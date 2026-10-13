"""Command-line interface untuk cuciin."""

import sys
from rich.console import Console
from rich.table import Table

from cuciin.database import get_connection, init_db
from cuciin.models import Order, HARGA, STATUS_FLOW, rak_kosong

console = Console()


def tambah(args):
    """cuciin tambah <nama> <berat> <layanan> [no_hp]"""
    if len(args) < 3:
        console.print("[red]usage:[/red] cuciin tambah <nama> <berat> <layanan> [no_hp]")
        return

    nama = args[0]
    try:
        berat = float(args[1])
    except ValueError:
        console.print("[red]berat harus angka[/red]")
        return
    layanan = args[2]
    no_hp = args[3] if len(args) > 3 else ""

    if layanan not in HARGA:
        console.print(f"[red]layanan gak ada.[/red] pilihan: {', '.join(HARGA)}")
        return

    conn = get_connection()

    rak = rak_kosong(conn)
    if rak is None:
        console.print("[red]rak penuh![/red] selesaikan order dulu")
        conn.close()
        return

    order = Order.buat(nama, no_hp, berat, layanan)
    order.no_rak = rak

    conn.execute(
        """INSERT INTO orders (nama, no_hp, berat, layanan, harga, status, no_rak, sudah_bayar, jumlah_bayar)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (order.nama, order.no_hp, order.berat, order.layanan, order.harga,
         order.status, order.no_rak, order.sudah_bayar, order.jumlah_bayar),
    )
    conn.commit()
    conn.close()

    console.print(f"[green]✓[/green] {nama} — {berat}kg — {layanan} — [bold]Rp{order.harga:,}[/bold] — rak [cyan]{rak}[/cyan]")


def list_order(args):
    """cuciin list"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
    conn.close()

    if not rows:
        console.print("[dim]belum ada order.[/dim]")
        return

    table = Table(title="cuciin")
    table.add_column("id", style="cyan")
    table.add_column("nama")
    table.add_column("berat", justify="right")
    table.add_column("layanan")
    table.add_column("harga", justify="right", style="green")
    table.add_column("rak", style="magenta")
    table.add_column("status", style="yellow")
    table.add_column("bayar", justify="right")

    for r in rows:
        if r["sudah_bayar"]:
            bayar = "[green]lunas[/green]"
        else:
            kurang = r["harga"] - r["jumlah_bayar"]
            bayar = f"[red]-Rp{kurang:,}[/red]"

        table.add_row(
            str(r["id"]), r["nama"], f"{r['berat']}kg",
            r["layanan"], f"Rp{r['harga']:,}",
            r["no_rak"] or "-", r["status"], bayar,
        )

    console.print(table)


def status(args):
    """cuciin status <id> — majuin status"""
    if not args:
        console.print("[red]usage:[/red] cuciin status <id>")
        return

    try:
        order_id = int(args[0])
    except ValueError:
        console.print("[red]id harus angka[/red]")
        return

    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if not row:
        console.print(f"[red]order #{order_id} gak ada[/red]")
        conn.close()
        return

    current = row["status"]
    idx = STATUS_FLOW.index(current)

    if idx + 1 >= len(STATUS_FLOW):
        console.print(f"[yellow]order #{order_id} udah diambil, gak bisa maju lagi[/yellow]")
        conn.close()
        return

    next_stat = STATUS_FLOW[idx + 1]

    # Kalau maju ke 'diambil', set diambil_at & kosongin rak
    if next_stat == "diambil":
        conn.execute(
            "UPDATE orders SET status = ?, diambil_at = CURRENT_TIMESTAMP, no_rak = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (next_stat, order_id),
        )
        console.print(f"[green]✓[/green] order #{order_id}: {current} → {next_stat} (rak {row['no_rak']} kosong)")
    else:
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (next_stat, order_id),
        )
        console.print(f"[green]✓[/green] order #{order_id}: {current} → {next_stat}")

    conn.commit()
    conn.close()


def bayar(args):
    """cuciin bayar <id> <jumlah> — catat pembayaran"""
    if len(args) < 2:
        console.print("[red]usage:[/red] cuciin bayar <id> <jumlah>")
        return

    try:
        order_id = int(args[0])
        jumlah = int(args[1])
    except ValueError:
        console.print("[red]id & jumlah harus angka[/red]")
        return

    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if not row:
        console.print(f"[red]order #{order_id} gak ada[/red]")
        conn.close()
        return

    total_bayar = row["jumlah_bayar"] + jumlah
    sudah_bayar = 1 if total_bayar >= row["harga"] else 0

    conn.execute(
        "UPDATE orders SET jumlah_bayar = ?, sudah_bayar = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (total_bayar, sudah_bayar, order_id),
    )
    conn.commit()
    conn.close()

    sisa = row["harga"] - total_bayar
    if sisa <= 0:
        console.print(f"[green]✓[/green] order #{order_id} [bold]LUNAS[/bold]")
    else:
        console.print(f"[green]✓[/green] order #{order_id} bayar Rp{jumlah:,} — sisa [red]Rp{sisa:,}[/red]")


def hapus(args):
    """cuciin hapus <id>"""
    if not args:
        console.print("[red]usage:[/red] cuciin hapus <id>")
        return

    try:
        order_id = int(args[0])
    except ValueError:
        console.print("[red]id harus angka[/red]")
        return

    conn = get_connection()
    cur = conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        console.print(f"[red]order #{order_id} gak ada[/red]")
    else:
        console.print(f"[green]✓[/green] order #{order_id} dihapus")


def rak(args):
    """cuciin rak — lihat status rak"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT no_rak, nama FROM orders WHERE status != 'diambil' AND no_rak IS NOT NULL"
    ).fetchall()
    conn.close()

    kepake = {r["no_rak"]: r["nama"] for r in rows}

    from cuciin.models import semua_rak
    table = Table(title="status rak")
    table.add_column("rak", style="magenta")
    table.add_column("status")
    table.add_column("isi")

    for r in semua_rak():
        if r in kepake:
            table.add_row(r, "[red]terisi[/red]", kepake[r])
        else:
            table.add_row(r, "[green]kosong[/green]", "-")

    console.print(table)


def help_cmd(args=None):
    """cuciin help"""
    console.print("""
[bold cyan]cuciin[/bold cyan] — sistem manajemen laundry

[bold]Command:[/bold]
  cuciin tambah <nama> <berat> <layanan> [no_hp]   tambah order
  cuciin list                                      lihat semua order
  cuciin status <id>                               majuin status
  cuciin bayar <id> <jumlah>                       catat pembayaran
  cuciin rak                                       lihat status rak
  cuciin hapus <id>                                hapus order
  cuciin help                                      bantuan

[bold]Layanan:[/bold]
  cuci-kering     Rp7.000/kg
  cuci-setrika    Rp10.000/kg
  express         Rp15.000/kg

[bold]Status flow:[/bold]
  dicuci → dikeringin → disetrika → ready → diambil
""")


COMMANDS = {
    "tambah": tambah,
    "list": list_order,
    "status": status,
    "bayar": bayar,
    "rak": rak,
    "hapus": hapus,
    "help": help_cmd,
}


def main():
    init_db()

    args = sys.argv[1:]
    if not args:
        help_cmd()
        return

    cmd = args[0]
    if cmd not in COMMANDS:
        console.print(f"[red]command gak dikenal:[/red] {cmd}")
        console.print("coba: cuciin help")
        return

    COMMANDS[cmd](args[1:])


if __name__ == "__main__":
    main()