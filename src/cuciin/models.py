"""Model & logika bisnis untuk cuciin."""

from dataclasses import dataclass

# Harga per kg
HARGA = {
    "cuci-kering": 7000,
    "cuci-setrika": 10000,
    "express": 15000,
}

# Urutan status
STATUS_FLOW = ["dicuci", "dikeringin", "disetrika", "ready", "diambil"]

# Kapasitas rak
MAX_RAK = 20


def semua_rak() -> list[str]:
    """Generate daftar rak: A1, A2, ... A20."""
    return [f"A{i}" for i in range(1, MAX_RAK + 1)]


def rak_kosong(conn) -> str | None:
    """Cari rak kosong pertama."""
    rows = conn.execute(
        "SELECT no_rak FROM orders WHERE status != 'diambil' AND no_rak IS NOT NULL"
    ).fetchall()
    kepake = {r["no_rak"] for r in rows}

    for rak in semua_rak():
        if rak not in kepake:
            return rak
    return None  # rak penuh


@dataclass
class Order:
    id: int | None
    nama: str
    no_hp: str
    berat: float
    layanan: str
    harga: int
    status: str = "dicuci"
    no_rak: str | None = None
    sudah_bayar: int = 0
    jumlah_bayar: int = 0

    @classmethod
    def hitung_harga(cls, layanan: str, berat: float) -> int:
        """Hitung harga otomatis berdasarkan layanan & berat."""
        if layanan not in HARGA:
            raise ValueError(f"layanan gak ada: {layanan}")
        return int(HARGA[layanan] * berat)

    @classmethod
    def buat(cls, nama: str, no_hp: str, berat: float, layanan: str) -> "Order":
        """Factory: bikin order baru + hitung harga otomatis."""
        harga = cls.hitung_harga(layanan, berat)
        return cls(
            id=None,
            nama=nama,
            no_hp=no_hp,
            berat=berat,
            layanan=layanan,
            harga=harga,
            status="dicuci",
        )

    def kekurangan(self) -> int:
        """Berapa yang masih kurang."""
        return max(0, self.harga - self.jumlah_bayar)

    def next_status(self) -> str | None:
        """Status selanjutnya. None kalau udah di akhir."""
        idx = STATUS_FLOW.index(self.status)
        if idx + 1 < len(STATUS_FLOW):
            return STATUS_FLOW[idx + 1]
        return None