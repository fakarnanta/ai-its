from PIL import Image, ImageDraw, ImageFont

# 1. Load gambar asli
input_path = "interface mathventure.jpg"  # Pastikan nama file sesuai
output_path = "mathventure_start_800x600.jpg"

try:
    img = Image.open(input_path)
    
    # 2. Ubah ukuran menjadi tepat 800x600 (Resize)
    # Menggunakan LANCZOS untuk kualitas terbaik saat resize
    img = img.resize((800, 600), Image.Resampling.LANCZOS)
    
    # 3. Siapkan alat gambar
    draw = ImageDraw.Draw(img, "RGBA")
    
    # 4. Definisikan properti tombol "Start"
    # Posisi tengah
    center_x, center_y = 800 // 2, 600 // 2
    btn_width, btn_height = 200, 80
    
    # Koordinat tombol (kiri-atas, kanan-bawah)
    x1 = center_x - btn_width // 2
    y1 = center_y - btn_height // 2
    x2 = center_x + btn_width // 2
    y2 = center_y + btn_height // 2
    
    # Warna tombol (Gaya RPG Kayu/Coklat)
    btn_fill = (139, 69, 19, 255)    # SaddleBrown
    btn_outline = (80, 40, 10, 255)  # Darker Brown
    text_color = (255, 215, 0, 255)  # Gold
    
    # Gambar tombol dengan sudut melengkung (rounded)
    draw.rounded_rectangle(
        (x1, y1, x2, y2),
        radius=20,
        fill=btn_fill,
        outline=btn_outline,
        width=5
    )
    
    # 5. Tambahkan Teks "START"
    # Coba load font default atau font sistem jika ada, jika tidak gunakan default
    try:
        # Jalur font umum di Linux/Windows, sesuaikan jika ingin font khusus RPG
        # font = ImageFont.truetype("arial.ttf", 40) 
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40) 
    except IOError:
        font = ImageFont.load_default()

    text = "START"
    
    # Hitung posisi teks agar benar-benar di tengah tombol
    # Menggunakan anchor "mm" (middle-middle) untuk centering yang presisi
    draw.text((center_x, center_y), text, fill=text_color, font=font, anchor="mm")
    
    # 6. Simpan hasil
    img.save(output_path)
    print(f"Berhasil! Gambar disimpan sebagai {output_path} dengan ukuran 800x600.")
    img.show()

except Exception as e:
    print(f"Terjadi kesalahan: {e}")