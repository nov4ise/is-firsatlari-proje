# -*- coding: utf-8 -*-
"""
İŞ FIRSATLARI | Türkiye İş ve Kamu Alım Takip Merkezi
Windows masaüstü uygulaması. İlan keşfi için Google Haberler RSS araması kullanır;
ilan bağlantıları kaynak sitelere yönlendirir. Resmî başvuru ve şartlar için kaynak ilanı esas alın.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import webbrowser, sqlite3, os, sys, re, html

APP_NAME = "İŞ FIRSATLARI"
APP_VERSION = "1.0.0"
DB_NAME = "is_firsatlari.db"

CATEGORIES = {
    "Eski Hükümlü Alımları": [
        '"eski hükümlü" işçi alımı Türkiye',
        '"eski hükümlü/TMY" alım ilanı',
        '"eski hükümlü" personel alımı site:gov.tr OR site:edu.tr OR site:bel.tr',
    ],
    "Kamu İşçi Alımları": [
        'kamu sürekli işçi alımı İŞKUR ilanı Türkiye',
        'kamu geçici işçi alımı ilanı site:gov.tr OR site:edu.tr',
    ],
    "Memur ve Sözleşmeli Personel": [
        'kamu personel alımı memur sözleşmeli personel Kariyer Kapısı',
        'personel alım ilanı site:kariyerkapisi.gov.tr',
    ],
    "Belediye Alımları": [
        'belediye personel işçi alımı ilanı Türkiye',
        'belediye şirketi personel alımı ilanı',
    ],
    "Üniversite Alımları": [
        'üniversite personel alımı işçi memur sözleşmeli ilanı Türkiye',
        'site:edu.tr personel alım ilanı',
    ],
    "İŞKUR Özel Sektör": [
        'İŞKUR açık iş ilanları Türkiye iş ilanı',
        'İŞKUR iş ilanı personel alımı Türkiye',
    ],
    "KPSS'siz ve Diğer Alımlar": [
        'KPSS şartı aranmadan kamu personel alımı ilanı',
        'KPSS şartsız işçi alımı Türkiye',
    ],
}

OFFICIAL_LINKS = [
    ("İŞKUR Açık İş İlanları", "https://esube.iskur.gov.tr/istihdam/AcikIsIlanAra.aspx"),
    ("Kariyer Kapısı – Kamu İşe Alım", "https://kariyerkapisi.gov.tr/isealim"),
    ("SBB Kamu İlanları", "https://kamuilan.sbb.gov.tr/"),
    ("Resmî Gazete", "https://www.resmigazete.gov.tr/"),
    ("İlan.gov.tr", "https://www.ilan.gov.tr/"),
    ("ÖSYM", "https://www.osym.gov.tr/"),
]

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def clean_text(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

def source_name(url):
    host = (urlparse(url).netloc or "").lower()
    host = host.replace("www.", "")
    return host or "Kaynak bağlantısı"

def parse_date(value):
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value or "Tarih belirtilmemiş"

def make_rss_url(query):
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"

class Store:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS listings (
            link TEXT PRIMARY KEY, title TEXT, category TEXT, source TEXT,
            published TEXT, description TEXT, status TEXT DEFAULT 'Takip edilecek',
            favorite INTEGER DEFAULT 0, first_seen TEXT
        )""")
        self.conn.commit()

    def upsert(self, item):
        self.conn.execute("""INSERT INTO listings
            (link,title,category,source,published,description,status,favorite,first_seen)
            VALUES (?,?,?,?,?,?, 'Takip edilecek',0,?)
            ON CONFLICT(link) DO UPDATE SET
            title=excluded.title, category=excluded.category, source=excluded.source,
            published=excluded.published, description=excluded.description""",
            (item["link"], item["title"], item["category"], item["source"],
             item["published"], item["description"], datetime.now().isoformat(timespec="seconds")))
        self.conn.commit()

    def all(self):
        cur = self.conn.execute("""SELECT link,title,category,source,published,description,status,favorite
                                   FROM listings ORDER BY rowid DESC""")
        return cur.fetchall()

    def update_status(self, link, status):
        self.conn.execute("UPDATE listings SET status=? WHERE link=?", (status, link))
        self.conn.commit()

    def toggle_favorite(self, link):
        self.conn.execute("UPDATE listings SET favorite=1-favorite WHERE link=?", (link,))
        self.conn.commit()

    def export_rows(self):
        return self.all()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} | Türkiye İş ve Kamu Alım Takip Merkezi")
        self.geometry("1320x820")
        self.minsize(1050, 680)
        self.configure(bg="#eef2f7")
        try:
            from PIL import Image, ImageTk
            logo_file = os.path.join(app_dir(), "logo_is_firsatlari.png")
            if os.path.exists(logo_file):
                self._logo_img = ImageTk.PhotoImage(Image.open(logo_file).resize((64, 64)))
                self.iconphoto(True, self._logo_img)
        except Exception:
            pass
        self.store = Store(os.path.join(app_dir(), DB_NAME))
        self.items = []
        self.filtered = []
        self.busy = False
        self._style()
        self._build()
        self.refresh_table()
        self.after(900, self.refresh_async)

    def _style(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("Treeview", background="white", fieldbackground="white",
                        foreground="#1e293b", rowheight=34, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#e7edf5", foreground="#24364b",
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#dbeafe")],
                  foreground=[("selected", "#10243a")])
        style.configure("TCombobox", padding=6)
        style.configure("TButton", padding=7, font=("Segoe UI", 9, "bold"))

    def _build(self):
        header = tk.Frame(self, bg="#13263f", height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="▣  İŞ FIRSATLARI", bg="#13263f", fg="white",
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=24, pady=(13,0))
        tk.Label(header, text="TÜRKİYE İŞ VE KAMU ALIM TAKİP MERKEZİ  •  TÜRKÇE MASAÜSTÜ UYGULAMASI",
                 bg="#13263f", fg="#b8c8dc", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=27)

        top = tk.Frame(self, bg="#eef2f7")
        top.pack(fill="x", padx=18, pady=(14,8))
        self.stat_total = self._stat(top, "BULUNAN İLAN", "0", "#1d4ed8")
        self.stat_old = self._stat(top, "ESKİ HÜKÜMLÜ", "0", "#0f766e")
        self.stat_public = self._stat(top, "KAMU / BELEDİYE", "0", "#7c3aed")
        self.stat_fav = self._stat(top, "FAVORİ", "0", "#b45309")

        controls = tk.Frame(self, bg="white", padx=12, pady=11,
                            highlightbackground="#d9e1eb", highlightthickness=1)
        controls.pack(fill="x", padx=18, pady=5)
        tk.Label(controls, text="Ara:", bg="white", fg="#334155",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(controls, textvariable=self.search_var, width=30)
        ent.pack(side="left", padx=(7,14))
        ent.bind("<KeyRelease>", lambda e: self.refresh_table())
        tk.Label(controls, text="Kategori:", bg="white", fg="#334155").pack(side="left")
        self.cat_var = tk.StringVar(value="Tüm kategoriler")
        cat = ttk.Combobox(controls, textvariable=self.cat_var, state="readonly", width=26,
                          values=["Tüm kategoriler"] + list(CATEGORIES.keys()))
        cat.pack(side="left", padx=(7,14))
        cat.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        tk.Label(controls, text="Durum:", bg="white", fg="#334155").pack(side="left")
        self.status_var = tk.StringVar(value="Tümü")
        status = ttk.Combobox(controls, textvariable=self.status_var, state="readonly", width=17,
                              values=["Tümü","Takip edilecek","Başvurulacak","Başvuruldu","Uygun değil"])
        status.pack(side="left", padx=(7,14))
        status.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        self.fav_only = tk.BooleanVar(value=False)
        tk.Checkbutton(controls, text="Yalnız favoriler", variable=self.fav_only,
                       bg="white", command=self.refresh_table).pack(side="left", padx=5)
        self.refresh_btn = tk.Button(controls, text="↻  İLANLARI GÜNCELLE",
                    bg="#1d4ed8", fg="white", activebackground="#1e40af",
                    activeforeground="white", relief="flat", padx=13, pady=8,
                    font=("Segoe UI",9,"bold"), command=self.refresh_async)
        self.refresh_btn.pack(side="right")

        main = tk.Frame(self, bg="#eef2f7")
        main.pack(fill="both", expand=True, padx=18, pady=(7,12))
        left = tk.Frame(main, bg="white", width=205, highlightbackground="#d9e1eb", highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0,10))
        left.pack_propagate(False)
        tk.Label(left, text="RESMÎ KAYNAKLAR", bg="white", fg="#64748b",
                 font=("Segoe UI",8,"bold")).pack(anchor="w", padx=13, pady=(14,8))
        for label, url in OFFICIAL_LINKS:
            b = tk.Button(left, text="↗  "+label, anchor="w", bg="white", fg="#1e3a5f",
                          activebackground="#eff6ff", relief="flat", padx=12, pady=7,
                          font=("Segoe UI",9), command=lambda u=url: webbrowser.open(u))
            b.pack(fill="x", padx=5)
        tk.Frame(left, bg="#e2e8f0", height=1).pack(fill="x", padx=12, pady=12)
        tk.Label(left, text="İPUCU", bg="white", fg="#0f766e",
                 font=("Segoe UI",8,"bold")).pack(anchor="w", padx=13)
        tk.Label(left, text="İlanı seçip “İlan bağlantısını aç” düğmesine bas. Başvuru şartlarını mutlaka resmî ilandan doğrula.",
                 bg="white", fg="#64748b", justify="left", wraplength=170,
                 font=("Segoe UI",8)).pack(anchor="w", padx=13, pady=7)

        right = tk.Frame(main, bg="white", highlightbackground="#d9e1eb", highlightthickness=1)
        right.pack(side="left", fill="both", expand=True)
        titlebar = tk.Frame(right, bg="white")
        titlebar.pack(fill="x", padx=13, pady=(12,7))
        tk.Label(titlebar, text="GÜNCEL İLAN AKIŞI", bg="white", fg="#1e293b",
                 font=("Segoe UI",12,"bold")).pack(side="left")
        self.count_label = tk.Label(titlebar, text="0 ilan", bg="white", fg="#64748b")
        self.count_label.pack(side="right")
        cols = ("title","category","source","published","status","favorite")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        headings = {"title":"İLAN BAŞLIĞI","category":"KATEGORİ","source":"KAYNAK",
                    "published":"YAYIN TARİHİ","status":"TAKİP DURUMU","favorite":"★"}
        widths = {"title":390,"category":175,"source":145,"published":120,"status":125,"favorite":38}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], minwidth=55, anchor="w" if c=="title" else "center")
        yscroll = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(12,0), pady=(0,5))
        yscroll.pack(side="right", fill="y", padx=(0,10), pady=(0,5))
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        self.tree.bind("<Double-1>", lambda e: self.open_selected())

        actions = tk.Frame(right, bg="#f8fafc", padx=12, pady=10)
        actions.pack(fill="x", side="bottom")
        tk.Button(actions, text="İlan bağlantısını aç ↗", bg="#1d4ed8", fg="white",
                  relief="flat", padx=12, pady=7, command=self.open_selected).pack(side="left")
        tk.Button(actions, text="☆ Favoriye ekle / çıkar", bg="#e2e8f0", fg="#1e293b",
                  relief="flat", padx=10, pady=7, command=self.favorite_selected).pack(side="left", padx=7)
        self.new_status = tk.StringVar(value="Başvurulacak")
        ttk.Combobox(actions, textvariable=self.new_status, state="readonly", width=17,
                     values=["Takip edilecek","Başvurulacak","Başvuruldu","Uygun değil"]).pack(side="left", padx=(8,4))
        tk.Button(actions, text="Durumu kaydet", bg="#fef3c7", fg="#92400e",
                  relief="flat", padx=9, pady=7, command=self.save_status).pack(side="left")
        tk.Button(actions, text="Excel'e aktar", bg="#dcfce7", fg="#166534",
                  relief="flat", padx=10, pady=7, command=self.export_excel).pack(side="right")
        self.detail = tk.Label(right, text="Bir ilan seçerek açıklamasını ve kaynak bağlantısını görüntüleyebilirsin.",
                               bg="#f8fafc", fg="#475569", anchor="w", justify="left",
                               wraplength=950, padx=14, pady=9, font=("Segoe UI",9))
        self.detail.pack(fill="x", side="bottom")
        footer = tk.Frame(self, bg="#e8eef5")
        footer.pack(fill="x", side="bottom")
        self.status_label = tk.Label(footer, text="Hazır • Güncel ilanları görmek için “İlanları Güncelle” düğmesine bas.",
                                     bg="#e8eef5", fg="#475569", anchor="w", font=("Segoe UI",8))
        self.status_label.pack(fill="x", padx=20, pady=6)

    def _stat(self, parent, label, value, color):
        f = tk.Frame(parent, bg="white", padx=14, pady=9,
                     highlightbackground="#d9e1eb", highlightthickness=1)
        f.pack(side="left", fill="x", expand=True, padx=(0,8))
        tk.Label(f, text=label, bg="white", fg="#64748b",
                 font=("Segoe UI",8,"bold")).pack(anchor="w")
        v = tk.Label(f, text=value, bg="white", fg=color, font=("Segoe UI",18,"bold"))
        v.pack(anchor="w")
        return v

    def refresh_async(self):
        if self.busy: return
        self.busy = True
        self.refresh_btn.configure(state="disabled", text="GÜNCELLENİYOR…")
        self.status_label.configure(text="Kaynaklar taranıyor… İnternet bağlantısı ve kaynakların erişimi süreyi etkileyebilir.")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        found, errors = [], 0
        headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) IsFirsatlari/1.0"}
        for category, queries in CATEGORIES.items():
            for query in queries:
                try:
                    req = urllib.request.Request(make_rss_url(query), headers=headers)
                    with urllib.request.urlopen(req, timeout=18) as resp:
                        raw = resp.read()
                    root = ET.fromstring(raw)
                    for node in root.findall(".//item"):
                        title = clean_text(node.findtext("title", ""))
                        link = (node.findtext("link", "") or "").strip()
                        desc = clean_text(node.findtext("description", ""))
                        pub = parse_date(node.findtext("pubDate", ""))
                        if not title or not link: continue
                        source_el = node.find("source")
                        source = clean_text(source_el.text if source_el is not None else "") or source_name(link)
                        item = {"title":title, "link":link, "category":category,
                                "source":source, "published":pub, "description":desc}
                        found.append(item)
                except Exception:
                    errors += 1
        unique = {}
        for item in found:
            unique[item["link"]] = item
        for item in unique.values():
            self.store.upsert(item)
        self.after(0, lambda: self._fetch_done(len(unique), errors))

    def _fetch_done(self, count, errors):
        self.busy = False
        self.refresh_btn.configure(state="normal", text="↻  İLANLARI GÜNCELLE")
        self.refresh_table()
        msg = f"Güncelleme tamamlandı • {count} yeni/yenilenen sonuç"
        if errors: msg += f" • {errors} arama başarısız (kaynak engeli veya bağlantı sorunu olabilir)"
        self.status_label.configure(text=msg)

    def refresh_table(self):
        rows = self.store.all()
        q = self.search_var.get().casefold().strip()
        cat = self.cat_var.get()
        status = self.status_var.get()
        self.filtered = []
        for r in rows:
            link,title,category,source,published,desc,st,fav = r
            if cat != "Tüm kategoriler" and category != cat: continue
            if status != "Tümü" and st != status: continue
            if self.fav_only.get() and not fav: continue
            if q and q not in " ".join([title,category,source,desc]).casefold(): continue
            self.filtered.append(r)
        for iid in self.tree.get_children(): self.tree.delete(iid)
        for i,r in enumerate(self.filtered):
            link,title,category,source,published,desc,st,fav = r
            self.tree.insert("", "end", iid=str(i), values=(title,category,source,published,st,"★" if fav else ""))
        total = len(rows)
        old = sum(1 for r in rows if r[2] == "Eski Hükümlü Alımları")
        public = sum(1 for r in rows if r[2] in ("Kamu İşçi Alımları","Memur ve Sözleşmeli Personel","Belediye Alımları","Üniversite Alımları"))
        favorites = sum(1 for r in rows if r[7])
        self.stat_total.configure(text=str(total))
        self.stat_old.configure(text=str(old))
        self.stat_public.configure(text=str(public))
        self.stat_fav.configure(text=str(favorites))
        self.count_label.configure(text=f"{len(self.filtered)} sonuç gösteriliyor")

    def selected_row(self):
        sel = self.tree.selection()
        if not sel: return None
        try: return self.filtered[int(sel[0])]
        except Exception: return None

    def show_detail(self, _event=None):
        r = self.selected_row()
        if not r: return
        link,title,category,source,published,desc,status,fav = r
        text = f"{title}   |   {category}   |   {source}   |   Yayın: {published}\\n"
        text += (desc[:650] + ("…" if len(desc)>650 else "")) if desc else "Açıklama arama sonucunda alınamadı. Ayrıntılar için kaynak ilanı açın."
        self.detail.configure(text=text)

    def open_selected(self):
        r = self.selected_row()
        if not r:
            messagebox.showinfo("İlan seçilmedi", "Önce listeden bir ilan seç.")
            return
        webbrowser.open(r[0])

    def favorite_selected(self):
        r = self.selected_row()
        if not r: return
        self.store.toggle_favorite(r[0])
        self.refresh_table()

    def save_status(self):
        r = self.selected_row()
        if not r:
            messagebox.showinfo("İlan seçilmedi", "Önce listeden bir ilan seç.")
            return
        self.store.update_status(r[0], self.new_status.get())
        self.refresh_table()
        self.status_label.configure(text="İlan takip durumu kaydedildi.")

    def export_excel(self):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            messagebox.showerror("Eksik bileşen", "Excel aktarımı için openpyxl kurulmalı.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                    filetypes=[("Excel dosyası","*.xlsx")], initialfile="is_ilanlari.xlsx")
        if not path: return
        wb = Workbook(); ws = wb.active; ws.title = "İş İlanları"
        headers = ["İlan başlığı","Kategori","Kaynak sitesi","Yayın tarihi","Takip durumu","Favori","İlan bağlantısı","Açıklama"]
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True,color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="17324F")
        for r in self.filtered:
            link,title,category,source,published,desc,status,fav = r
            ws.append([title,category,source,published,status,"Evet" if fav else "Hayır",link,desc])
            cell = ws.cell(ws.max_row,7)
            cell.hyperlink = link; cell.style = "Hyperlink"
        for col,w in {"A":58,"B":30,"C":28,"D":20,"E":20,"F":12,"G":65,"H":85}.items():
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        wb.save(path)
        messagebox.showinfo("Aktarım tamamlandı", f"{len(self.filtered)} ilan Excel dosyasına aktarıldı.")

if __name__ == "__main__":
    App().mainloop()
