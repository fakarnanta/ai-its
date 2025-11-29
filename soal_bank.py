import os
import importlib.util
import sys

# --- KONFIGURASI ---
# Dictionary ini akan diisi otomatis berdasarkan NAMA FILE
SOAL_BANK = {}

def format_nama_folder(filename):
    """
    Mengubah nama file jelek menjadi nama Folder cantik.
    Contoh: 'osk_2010_bali.py'  --->  'OSK 2010 BALI'
    """
    nama = filename.replace(".py", "") # Hapus .py
    nama = nama.replace("_", " ")      # Ganti garis bawah jadi spasi
    return nama.upper()                # Huruf besar semua biar keren

def load_all_questions():
    # Cari folder 'bank_data'
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(base_dir, "bank_data")
    
    if not os.path.exists(folder_path):
        print(f"❌ ERROR: Folder '{folder_path}' tidak ditemukan.")
        return

    files = os.listdir(folder_path)
    print(f"DEBUG: Menemukan {len(files)} file di bank_data.")

    for filename in files:
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            file_path = os.path.join(folder_path, filename)
            
            try:
                # Load module secara dinamis
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Ambil soal dan masukkan ke bank
                if hasattr(module, "LIST_SOAL"):
                    tambah_ke_bank(module.LIST_SOAL, filename)
                    print(f"   -> Meload: {filename} ... OK!")
                else:
                    print(f"   -> Skip: {filename} (Tidak ada LIST_SOAL)")
                    
            except Exception as e:
                print(f"ERROR pada file {filename}: {e}")

def tambah_ke_bank(daftar_soal, filename):
    # LANGKAH KUNCI: Gunakan nama file sebagai KATEGORI UTAMA (Folder)
    nama_folder = format_nama_folder(filename)
    
    # Jika folder belum ada, buat strukturnya
    if nama_folder not in SOAL_BANK:
        SOAL_BANK[nama_folder] = {
            "Sederhana": [], 
            "Dasar": [], 
            "Kompleks": []
        }
        
    # Masukkan soal ke folder tersebut berdasarkan levelnya
    for item in daftar_soal:
        level = item.get("level", "Dasar") # Default ke Dasar jika typo
        
        # Validasi agar tidak error jika level aneh
        if level not in SOAL_BANK[nama_folder]:
            level = "Dasar"
            
        # Kita simpan juga kategori aslinya (Bilangan/Geometri) di dalam data soal
        # barangkali nanti butuh buat filter tambahan.
        item['origin_file'] = filename
        
        SOAL_BANK[nama_folder][level].append(item)

# --- EKSEKUSI ---
print("--- MEMUAT BANK SOAL ---")
load_all_questions()
total_paket = len(SOAL_BANK)
total_soal = sum(len(v) for k in SOAL_BANK.values() for v in k.values())
print(f"INFO: Siap! Ada {total_paket} Paket Soal dengan total {total_soal} pertanyaan.")
print("--------------------------")