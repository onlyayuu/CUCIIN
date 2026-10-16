"""Web interface untuk cuciin pakai Flask."""

from flask import Flask, render_template, request, redirect, session, url_for, flash
from cuciin.database import get_connection, init_db, verify_admin
from cuciin.models import Order, HARGA, STATUS_FLOW, rak_kosong, semua_rak
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "cuciin-secret"


@app.before_request
def require_admin_login():
    if (
        request.path.startswith("/admin")
        and request.endpoint != "admin_login"
        and not session.get("is_admin")
    ):
        return redirect(url_for("admin_login"))


# ============ CUSTOMER ============

@app.route("/")
def index():
    """Landing page — form cek status."""
    return render_template("index.html")


@app.route("/cek", methods=["GET", "POST"])
def cek():
    """Cek status pesanan pakai no HP atau no nota."""
    if request.method == "POST":
        keyword = request.form.get("keyword", "").strip()
        if not keyword:
            flash("isi no HP atau no nota dulu", "error")
            return redirect(url_for("index"))
        return redirect(url_for("hasil", keyword=keyword))

    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return redirect(url_for("index"))

    conn = get_connection()
    cari_id = keyword.replace("#", "")
    if cari_id.isdigit():
        rows = conn.execute(
            "SELECT * FROM orders WHERE no_hp LIKE ? OR id = ? ORDER BY id DESC",
            (f"%{keyword}%", int(cari_id)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM orders WHERE no_hp LIKE ? ORDER BY id DESC",
            (f"%{keyword}%",),
        ).fetchall()
    conn.close()

    return render_template("hasil.html", keyword=keyword, orders=rows)


@app.route("/order/<int:order_id>")
def order_detail(order_id):
    """Detail order pelanggan — timeline visual."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()

    if not row:
        flash(f"order #{order_id} gak ketemu", "error")
        return redirect(url_for("index"))

    return render_template("order_detail.html", o=row)


@app.route("/order/<int:order_id>/nota")
def order_nota(order_id):
    """Nota versi pelanggan."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()

    if not row:
        flash(f"order #{order_id} gak ketemu", "error")
        return redirect(url_for("index"))

    return render_template("nota.html", o=row, now=datetime.now())


@app.route("/tambah", methods=["GET", "POST"])
def tambah():
    if request.method == "POST":
        nama = request.form["nama"]
        no_hp = request.form.get("no_hp", "")
        berat = float(request.form["berat"])
        layanan = request.form["layanan"]

        conn = get_connection()
        rak = rak_kosong(conn)
        if rak is None:
            conn.close()
            flash("rak penuh!", "error")
            return redirect(url_for("tambah"))

        order = Order.buat(nama, no_hp, berat, layanan)
        order.no_rak = rak

        cur = conn.execute(
            """INSERT INTO orders (nama, no_hp, berat, layanan, harga, status, no_rak, sudah_bayar, jumlah_bayar)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order.nama, order.no_hp, order.berat, order.layanan, order.harga,
             order.status, order.no_rak, order.sudah_bayar, order.jumlah_bayar),
        )
        order_id = cur.lastrowid
        conn.commit()
        conn.close()

        flash(f"order #{order_id} berhasil! simpan no nota kamu: #{order_id}", "success")
        return redirect(url_for("order_detail", order_id=order_id))

    return render_template("tambah.html", layanan=HARGA)


# ============ ADMIN ============

@app.route("/admin")
def admin():
    conn = get_connection()
    orders = conn.execute(
        "SELECT * FROM orders WHERE status != 'diambil' ORDER BY id DESC"
    ).fetchall()

    total_order = conn.execute("SELECT COUNT(*) as c FROM orders WHERE status != 'diambil'").fetchone()["c"]
    total_pendapatan = conn.execute("SELECT COALESCE(SUM(jumlah_bayar), 0) as s FROM orders").fetchone()["s"]
    total_piutang = conn.execute(
        "SELECT COALESCE(SUM(harga - jumlah_bayar), 0) as s FROM orders WHERE sudah_bayar = 0"
    ).fetchone()["s"]
    rak_terpakai = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE status != 'diambil' AND no_rak IS NOT NULL"
    ).fetchone()["c"]
    conn.close()

    stats = {
        "total_order": total_order,
        "pendapatan": total_pendapatan,
        "piutang": total_piutang,
        "rak_terpakai": rak_terpakai,
        "rak_total": len(semua_rak()),
    }
    return render_template("admin.html", orders=orders, stats=stats)


@app.route("/admin/bayar/<int:order_id>", methods=["POST"])
def admin_bayar(order_id):
    jumlah = int(request.form.get("jumlah", 0))

    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        flash(f"order #{order_id} gak ada", "error")
        return redirect(url_for("admin"))

    total_bayar = row["jumlah_bayar"] + jumlah
    sudah_bayar = 1 if total_bayar >= row["harga"] else 0

    conn.execute(
        "UPDATE orders SET jumlah_bayar = ?, sudah_bayar = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (total_bayar, sudah_bayar, order_id),
    )
    conn.commit()
    conn.close()
    flash(f"order #{order_id} bayar Rp{jumlah:,}", "success")
    return redirect(url_for("admin"))


@app.route("/admin/lunas/<int:order_id>")
def admin_lunas(order_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        flash(f"order #{order_id} gak ada", "error")
        return redirect(url_for("admin"))

    conn.execute(
        "UPDATE orders SET jumlah_bayar = harga, sudah_bayar = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (order_id,),
    )
    conn.commit()
    conn.close()
    flash(f"order #{order_id} lunas", "success")
    return redirect(url_for("admin"))


@app.route("/admin/status/<int:order_id>")
def admin_status(order_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if not row:
        conn.close()
        flash(f"order #{order_id} gak ada", "error")
        return redirect(url_for("admin"))

    current = row["status"]
    idx = STATUS_FLOW.index(current)

    if idx + 1 >= len(STATUS_FLOW):
        conn.close()
        flash(f"order #{order_id} udah diambil", "warning")
        return redirect(url_for("admin"))

    next_stat = STATUS_FLOW[idx + 1]

    if next_stat == "diambil":
        conn.execute(
            "UPDATE orders SET status = ?, diambil_at = CURRENT_TIMESTAMP, no_rak = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (next_stat, order_id),
        )
        flash(f"order #{order_id} diambil — rak {row['no_rak']} kosong", "success")
    else:
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (next_stat, order_id),
        )
        flash(f"order #{order_id}: {current} → {next_stat}", "success")

    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/nota/<int:order_id>")
def admin_nota(order_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()

    if not row:
        flash(f"order #{order_id} gak ada", "error")
        return redirect(url_for("admin"))

    return render_template("nota.html", o=row, now=datetime.now())


@app.route("/admin/rak")
def admin_rak():
    conn = get_connection()
    rows = conn.execute(
        "SELECT no_rak, nama, id FROM orders WHERE status != 'diambil' AND no_rak IS NOT NULL"
    ).fetchall()
    conn.close()

    kepake = {r["no_rak"]: {"nama": r["nama"], "id": r["id"]} for r in rows}

    rak_list = []
    for r in semua_rak():
        if r in kepake:
            rak_list.append({"no": r, "status": "terisi", "isi": kepake[r]})
        else:
            rak_list.append({"no": r, "status": "kosong", "isi": None})

    return render_template("rak.html", rak_list=rak_list)


@app.route("/admin/rekap")
def admin_rekap():
    conn = get_connection()
    periode = request.args.get("periode", "hari")
    today = datetime.now().date()

    if periode == "hari":
        start = today.strftime("%Y-%m-%d")
    elif periode == "minggu":
        start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    elif periode == "bulan":
        start = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        start = "1970-01-01"

    rows = conn.execute(
        "SELECT * FROM orders WHERE DATE(created_at) >= ? ORDER BY created_at DESC",
        (start,),
    ).fetchall()

    total_order = len(rows)
    total_nilai = sum(r["harga"] for r in rows)
    total_dibayar = sum(r["jumlah_bayar"] for r in rows)
    total_piutang = total_nilai - total_dibayar
    conn.close()

    rekap = {
        "periode": periode,
        "total_order": total_order,
        "total_nilai": total_nilai,
        "total_dibayar": total_dibayar,
        "total_piutang": total_piutang,
    }
    return render_template("rekap.html", rekap=rekap, orders=rows)


@app.route("/admin/arsip")
def admin_arsip():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM orders WHERE status = 'diambil' ORDER BY diambil_at DESC"
    ).fetchall()
    conn.close()
    return render_template("arsip.html", orders=rows)


@app.route("/admin/hapus/<int:order_id>")
def admin_hapus(order_id):
    conn = get_connection()
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash(f"order #{order_id} dihapus", "success")
    return redirect(url_for("admin"))


def main():
    init_db()
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if verify_admin(username, password):
            session["is_admin"] = True
            flash("Login berhasil", "success")
            return redirect(url_for("admin"))
        else:
            flash("Username atau password salah", "error")

    return render_template("login.html")