"""Web interface untuk cuciin pakai Flask."""

import csv
import io
from flask import Flask, Response, render_template, request, redirect, session, url_for, flash
from cuciin.database import get_connection, init_db, verify_admin
from cuciin.models import Order, HARGA, STATUS_FLOW, rak_kosong, semua_rak
from datetime import datetime, timedelta
import math

app = Flask(__name__, static_folder="assets", static_url_path="/assets")
app.secret_key = "cuciin-secret"


@app.before_request
def require_admin_login():
    if (
        request.path.startswith("/admin")
        and request.endpoint != "admin_login"
        and not session.get("is_admin")
    ):
        return redirect(url_for("admin_login"))


@app.route("/")
def index():
    return redirect(url_for("admin_login"))



# ============ ADMIN ============

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        no_hp = request.form.get("no_hp", "").strip()
        layanan = request.form.get("layanan", "")
        try:
            berat = float(request.form.get("berat", ""))
        except ValueError:
            flash("berat harus berupa angka yang lebih besar dari 0", "error")
            return redirect(url_for("admin"))

        if not nama:
            flash("nama pelanggan wajib diisi", "error")
            return redirect(url_for("admin"))
        if not math.isfinite(berat) or berat <= 0:
            flash("berat harus lebih besar dari 0", "error")
            return redirect(url_for("admin"))
        if layanan not in HARGA:
            flash("layanan tidak valid", "error")
            return redirect(url_for("admin"))

        conn = get_connection()
        rak = rak_kosong(conn)
        if rak is None:
            conn.close()
            flash("rak penuh!", "error")
            return redirect(url_for("admin"))

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
        flash(f"order #{order_id} berhasil ditambahkan — status Diproses", "success")
        return redirect(url_for("admin"))

    keyword = request.args.get("q", "").strip()
    conn = get_connection()
    if keyword:
        orders = conn.execute(
            """SELECT * FROM orders
               WHERE nama LIKE ? OR no_hp LIKE ?
               ORDER BY id DESC""",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
    else:
        orders = conn.execute(
            "SELECT * FROM orders WHERE NOT (status = 'selesai' AND sudah_bayar = 1) ORDER BY id DESC"
        ).fetchall()

    total_order = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE NOT (status = 'selesai' AND sudah_bayar = 1)"
    ).fetchone()["c"]
    total_pendapatan = conn.execute("SELECT COALESCE(SUM(jumlah_bayar), 0) as s FROM orders").fetchone()["s"]
    total_piutang = conn.execute(
        "SELECT COALESCE(SUM(harga - jumlah_bayar), 0) as s FROM orders WHERE sudah_bayar = 0"
    ).fetchone()["s"]
    rak_terpakai = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE no_rak IS NOT NULL"
    ).fetchone()["c"]
    conn.close()

    stats = {
        "total_order": total_order,
        "pendapatan": total_pendapatan,
        "piutang": total_piutang,
        "rak_terpakai": rak_terpakai,
        "rak_total": len(semua_rak()),
    }
    return render_template(
        "admin.html", orders=orders, stats=stats, layanan=HARGA, keyword=keyword
    )


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
        flash(f"order #{order_id} sudah selesai", "warning")
        return redirect(url_for("admin"))

    next_stat = STATUS_FLOW[idx + 1]

    if next_stat == "selesai":
        conn.execute(
            "UPDATE orders SET status = ?, no_rak = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (next_stat, order_id),
        )
        flash(f"order #{order_id} selesai — rak {row['no_rak']} kosong", "success")
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
        "SELECT no_rak, nama, id FROM orders WHERE status != 'selesai' AND no_rak IS NOT NULL"
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
    periode, start, end = _rekap_period()
    rows = _orders_for_rekap(start, end)

    total_order = len(rows)
    total_nilai = sum(r["harga"] for r in rows)
    total_dibayar = sum(r["jumlah_bayar"] for r in rows)
    total_piutang = total_nilai - total_dibayar

    rekap = {
        "periode": periode,
        "total_order": total_order,
        "total_nilai": total_nilai,
        "total_dibayar": total_dibayar,
        "total_piutang": total_piutang,
    }
    return render_template("rekap.html", rekap=rekap, orders=rows)


def _rekap_period():
    periode = request.args.get("periode", "hari")
    if periode not in ("hari", "minggu", "bulan", "semua"):
        periode = "hari"

    today = datetime.now().date()
    days = {"hari": 0, "minggu": 6, "bulan": 29}
    start = (today - timedelta(days=days[periode])).strftime("%Y-%m-%d") if periode != "semua" else None
    end = today.strftime("%Y-%m-%d") if start else None
    return periode, start, end


def _orders_for_rekap(start, end):
    conn = get_connection()
    try:
        query = "SELECT * FROM orders WHERE status = 'selesai'"
        params = ()
        if start is not None:
            query += " AND DATE(created_at) BETWEEN ? AND ?"
            params = (start, end)
        query += " ORDER BY updated_at DESC, id DESC"
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


@app.route("/admin/rekap/export")
def admin_rekap_export():
    periode, start, end = _rekap_period()
    orders = _orders_for_rekap(start, end)
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Nama", "No HP", "Layanan", "Berat (kg)", "Total",
        "Dibayar", "Sisa", "Status Pesanan", "Status Pembayaran",
        "Tanggal Masuk", "Tanggal Selesai",
    ])
    for order in orders:
        writer.writerow([
            order["id"], order["nama"], order["no_hp"] or "", order["layanan"],
            order["berat"], order["harga"], order["jumlah_bayar"],
            order["harga"] - order["jumlah_bayar"], order["status"],
            "Lunas" if order["sudah_bayar"] else "Belum",
            order["created_at"], order["updated_at"],
        ])

    filename = f"cuciin-rekap-{periode}-{datetime.now():%Y%m%d}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/admin/arsip")
def admin_arsip():
    return redirect(url_for("admin_rekap", periode="semua"))


@app.route("/admin/hapus/<int:order_id>")
def admin_hapus(order_id):
    conn = get_connection()
    conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    flash(f"order #{order_id} dihapus", "success")
    return redirect(url_for("admin"))


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


def main():
    init_db()
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()