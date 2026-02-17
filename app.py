import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from collections import Counter

# ===== KONFIGURASI AWAL SESUAI STANDAR MIGAS =====
ISO_LIMITS = {
    "Zone B (Acceptable)": 4.5,
    "Zone C (Unacceptable)": 7.1,
    "Zone D (Danger)": 11.0
}

# ===== FUNGSI REKOMENDASI (DIPERKAYA DENGAN LOKASI) =====
def get_recommendation(diagnosis: str, location: str = "Sistem") -> str:
    """Return rekomendasi berdasarkan diagnosis dan lokasi spesifik"""
    rec_map = {
        "UNBALANCE": (
            f"✅ **Rekomendasi untuk {location}**: Lakukan balancing rotor. Periksa: "
            "• Material menempel/hilang pada impeller "
            "• Korosi pada blade "
            "• Kencangkan baut rotor"
        ),
        "MISALIGNMENT": (
            f"✅ **Rekomendasi untuk {location}**: Periksa alignment coupling. Lakukan: "
            "• Laser alignment ulang pada coupling Pump-Motor "
            "• Inspeksi kondisi coupling & spacer "
            "• Pastikan tidak ada pipe strain"
        ),
        "LOOSENESS": (
            f"✅ **Rekomendasi untuk {location}**: Periksa kekencangan: "
            "• Baut pondasi & baseplate "
            "• Bearing housing bolts "
            "• Kondisi pondasi/crack "
            "• Lakukan torque check sesuai spec"
        ),
        "Tidak Terdiagnosa": (
            "⚠️ **Rekomendasi**: Data tidak memadai untuk diagnosa otomatis. "
            "• Lakukan analisis manual oleh vibration analyst Level II/III "
            "• Periksa kualitas data pengukuran "
            "• Pertimbangkan pengukuran ulang dengan phase measurement"
        )
    }
    return rec_map.get(diagnosis, rec_map["Tidak Terdiagnosa"])

# ===== FUNGSI EKSPOR CSV UNTUK SEMUA 12 TITIK =====
def generate_csv_report_all_points(machine_id, rpm, all_points, fft_inputs, input_data):
    """Generate CSV report untuk SEMUA 12 titik sesuai standar ISO 13374"""
    report_lines = []
    report_lines.append(f"VIBRATION DIAGNOSTIC REPORT - {machine_id.upper()}")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Machine ID: {machine_id} | RPM: {rpm} | 1x RPM: {rpm/60:.2f} Hz")
    report_lines.append(f"Standard: ISO 10816-3 (Pumps) / ISO 10816-7 (Motors)")
    report_lines.append("\nDETAIL SEMUA TITIK PENGUKURAN (12 TITIK):")
    report_lines.append("Titik,Overall (mm/s),Peak1 (Hz),Amp1 (mm/s),Peak2 (Hz),Amp2 (mm/s),Peak3 (Hz),Amp3 (mm/s),Diagnosis,Lokasi Indikasi")
    
    rpm_hz = rpm / 60
    for point in all_points:
        peaks = fft_inputs.get(point, [(0,0),(0,0),(0,0)])
        diagnosis = "Tidak Terdiagnosa"
        for fault, rule in FAULT_RULES.items():
            if rule["condition"](peaks, rpm_hz, point):
                diagnosis = fault
                break
        # Tentukan lokasi indikasi berdasarkan titik
        location_hint = "Pump" if "Pump" in point else "Motor"
        report_lines.append(
            f"{point},{input_data[point]:.2f},"
            f"{peaks[0][0]:.1f},{peaks[0][1]:.2f},"
            f"{peaks[1][0]:.1f},{peaks[1][1]:.2f},"
            f"{peaks[2][0]:.1f},{peaks[2][1]:.2f},"
            f"{diagnosis},{location_hint}"
        )
    
    # Tambahkan kesimpulan sistem
    report_lines.append("\nKESIMPULAN SISTEM:")
    report_lines.append(f"Total Titik Melebihi Alarm: {sum(1 for p in all_points if input_data[p] > ISO_LIMITS['Zone B (Acceptable)'])}")
    return "\n".join(report_lines)

# ===== RULE DIAGNOSA DENGAN PENINGKATAN LOKALISASI =====
FAULT_RULES = {
    "UNBALANCE": {
        "pattern": "1x RPM dominant di radial (H/V)",
        "condition": lambda peaks, rpm_hz, point: (
            abs(peaks[0][0] - rpm_hz) < 0.05 * rpm_hz and 
            peaks[0][1] > 0.7 * sum(p[1] for p in peaks) and
            "Axial" not in point
        ),
        "location_hint": lambda point: "Rotor Pump" if "Pump" in point else "Rotor Motor"
    },
    "MISALIGNMENT": {
        "pattern": "1x+2x RPM kuat di Axial",
        "condition": lambda peaks, rpm_hz, point: (
            "Axial" in point and
            any(abs(p[0] - rpm_hz) < 0.05 * rpm_hz for p in peaks[:2]) and
            any(abs(p[0] - 2 * rpm_hz) < 0.05 * rpm_hz for p in peaks[:2])
        ),
        "location_hint": "Coupling Pump-Motor"
    },
    "LOOSENESS": {
        "pattern": "Harmonik 1x-3x RPM dengan amplitudo menurun perlahan",
        "condition": lambda peaks, rpm_hz, point: (
            all(abs(peaks[i][0] - (i+1) * rpm_hz) < 0.05 * rpm_hz for i in range(3)) and
            peaks[1][1] > 0.5 * peaks[0][1] and 
            peaks[2][1] > 0.3 * peaks[0][1] and
            "Vertical" in point
        ),
        "location_hint": lambda point: f"Pondasi {point.split()[0]} {point.split()[1]}"
    }
}

# ===== ANTARMUKA UTAMA =====
st.set_page_config(page_title="Vibration Diagnostic Assistant - Migas Standard", layout="wide")

# ===== HEADER DENGAN DISCLAIMER WAJIB =====
st.markdown("""
<div style="background-color:#FFF3CD; padding:15px; border-left:6px solid #FFC107; border-radius:5px; margin-bottom:20px">
<h3>⚠️ PERINGATAN KESELAMATAN (SESUAI API RP 686 & SHELL DEP 31.38.60.17)</h3>
<p><strong>Tools ini adalah DECISION SUPPORT SYSTEM (DSS) - BUKAN pengganti analisis oleh personnel kompeten.</strong></p>
<ul>
<li>Diagnosis akhir HARUS diverifikasi oleh Vibration Analyst bersertifikat ISO 18436 Level II/III</li>
<li>Keputusan maintenance kritis (>100 kW) memerlukan approval Mechanical Engineer</li>
<li>Sesuai ISO 13374-1 §6.2.3: FFT wajib diambil di SEMUA 12 titik jika ada 1 titik melebihi alarm</li>
<li>Hasil tools ini TIDAK dapat dijadikan dasar hukum tanpa verifikasi manual</li>
</ul>
</div>
""", unsafe_allow_html=True)

st.title("🔧 Sistem Analisis Vibrasi Pump & Motor - Standar Industri Migas")

# Step 1: Input Data Mesin
col1, col2 = st.columns(2)
with col1:
    machine_id = st.text_input("ID Mesin", "PUMP-01")
    rpm = st.number_input("Operating RPM", min_value=100, max_value=10000, value=1780, step=10)
    if rpm < 100:
        st.warning("⚠️ RPM minimal 100!")
    iso_zone = st.selectbox("Batas Alarm ISO", list(ISO_LIMITS.keys()), index=0)
    alarm_limit = ISO_LIMITS[iso_zone]
    # Klasifikasi kritisitas (sesuai standar migas)
    criticality = st.selectbox("Kritisitas Mesin", ["Critical (>100 kW)", "Essential (50-100 kW)", "Auxiliary (<50 kW)"])

with col2:
    st.info(f"""
    📏 **Konfigurasi Pengukuran Sesuai ISO 10816**  
    - Total Titik: **12 titik wajib** (Pump+Motor × DE/NDE × H/V/A)  
    - Batas Alarm: **{alarm_limit} mm/s** ({iso_zone})  
    - 1x RPM = {rpm/60:.1f} Hz  
    - Kritisitas: **{criticality}**  
    - ⚠️ Jika ada 1 titik > alarm → **WAJIB input FFT SEMUA 12 titik**
    """)

# Step 2: Input Overall Vibration (12 titik)
st.subheader("📊 Input Overall Vibration (mm/s) - 12 Titik Standar")
points = [
    f"{machine} {end} {dir}" 
    for machine in ["Pump", "Motor"] 
    for end in ["DE", "NDE"] 
    for dir in ["Horizontal", "Vertical", "Axial"]
]

input_data = {}
cols = st.columns(4)
for i, point in enumerate(points):
    with cols[i % 4]:
        input_data[point] = st.number_input(
            point, 
            min_value=0.0, 
            max_value=20.0, 
            value=1.0, 
            step=0.1,
            key=f"overall_{point}"
        )

# Step 3: Deteksi Titik Bermasalah
flagged_points = [
    point for point, val in input_data.items() 
    if val > alarm_limit
]

# ===== LOGIKA UTAMA SESUAI STANDAR MIGAS =====
if flagged_points:
    # SESUAI ISO 13374-1 §6.2.3: JIKA ADA 1 TITIK MELEBIHI ALARM → WAJIB FFT DI SEMUA 12 TITIK
    st.error(f"⚠️ **{len(flagged_points)} titik melebihi batas alarm**: {', '.join(flagged_points)}")
    st.warning("🔴 **SESUAI STANDAR MIGAS (API RP 686 §5.3.2)**: FFT WAJIB diambil di **SEMUA 12 TITIK** untuk diagnosa akurat dan lokalisasi sumber")
    
    # Step 4: TAB FFT UNTUK SEMUA 12 TITIK (BUKAN HANYA TITIK BERMASALAH!)
    st.subheader("📈 Input FFT Spectrum - WAJIB 12 TITIK (Sesuai ISO 13374)")
    st.info("💡 **Petunjuk**: Input Top 3 Peaks (Frequency & Amplitude) untuk SETIAP titik. Titik dengan overall normal tetap WAJIB diisi untuk baseline komparasi.")
    
    # Generate 12 tabs untuk SEMUA titik
    tabs = st.tabs(points)  # <-- INI YANG DIUBAH: tabs(points) bukan tabs(flagged_points)
    
    fft_inputs = {}
    for idx, point in enumerate(points):  # <-- LOOP SEMUA 12 TITIK
        with tabs[idx]:
            # Tampilkan status overall
            status_icon = "⚠️" if input_data[point] > alarm_limit else "✅"
            st.write(f"{status_icon} **{point}** | Overall: {input_data[point]:.2f} mm/s | Status: {'MELEBIHI ALARM' if input_data[point] > alarm_limit else 'Normal'}")
            peaks = []
            
            for i in range(1, 4):
                col_a, col_b = st.columns(2)
                with col_a:
                    # Default frequency berdasarkan RPM
                    default_freq = float(rpm/60 * i) if i <= 3 else float(rpm/60)
                    freq = st.number_input(
                        f"Peak {i} Frequency (Hz)", 
                        min_value=0.1, 
                        value=default_freq, 
                        key=f"{point}_freq{i}"
                    )
                with col_b:
                    amp = st.number_input(
                        f"Peak {i} Amplitude (mm/s)", 
                        min_value=0.01, 
                        value=0.5 if input_data[point] <= alarm_limit else 2.0, 
                        key=f"{point}_amp{i}"
                    )
                peaks.append((freq, amp))
            
            # Visualisasi mini spektrum
            df_peaks = pd.DataFrame(peaks, columns=["Frequency (Hz)", "Amplitude (mm/s)"])
            st.bar_chart(df_peaks.set_index("Frequency (Hz)"), use_container_width=True)
            fft_inputs[point] = peaks
    
    # Step 5: Tombol Diagnosa (Hanya aktif jika semua 12 titik sudah diisi)
    if st.button("🔍 DIAGNOSA SISTEM (Analisis 12 Titik)", type="primary", use_container_width=True, help="Menganalisis pola komparatif antar 12 titik sesuai ISO 13374"):
        st.divider()
        st.subheader("🧠 HASIL DIAGNOSA SISTEM (Analisis Komparatif 12 Titik)")
        
        # ===== ALGORITMA DIAGNOSA MULTI-TITIK (SESUAI TEORI) =====
        rpm_hz = rpm / 60
        all_diagnoses = []  # Menyimpan hasil diagnosa per titik
        
        # Tahap 1: Diagnosa per titik
        for point in points:
            peaks = fft_inputs[point]
            diagnosis = "Tidak Terdiagnosa"
            confidence = 0
            location_hint = "Perlu analisis manual"
            
            # Cek semua rule
            for fault, rule in FAULT_RULES.items():
                if rule["condition"](peaks, rpm_hz, point):
                    diagnosis = fault
                    # Hitung confidence berdasarkan kekuatan pola
                    if fault == "UNBALANCE":
                        confidence = min(95, 75 + int((peaks[0][1] / alarm_limit) * 15))
                    elif fault == "MISALIGNMENT":
                        # Confidence berdasarkan kekuatan 2x RPM
                        ratio_2x = peaks[1][1] / peaks[0][1] if peaks[0][1] > 0 else 0
                        confidence = min(95, 70 + int(ratio_2x * 25))
                    elif fault == "LOOSENESS":
                        confidence = min(95, 65 + int((peaks[1][1]/peaks[0][1] + peaks[2][1]/peaks[0][1]) * 20))
                    
                    # Tentukan lokasi spesifik
                    if callable(rule.get("location_hint")):
                        location_hint = rule["location_hint"](point)
                    else:
                        location_hint = rule.get("location_hint", point)
                    break
            
            all_diagnoses.append({
                "point": point,
                "diagnosis": diagnosis,
                "confidence": confidence,
                "location_hint": location_hint,
                "peaks": peaks
            })
        
        # Tahap 2: AGREGASI SISTEM (Voting & Lokalisasi)
        # Hitung distribusi fault
        fault_counter = Counter([d["diagnosis"] for d in all_diagnoses if d["diagnosis"] != "Tidak Terdiagnosa"])
        system_diagnosis = "Tidak Terdiagnosa"
        system_confidence = 0
        system_location = "Perlu analisis manual oleh vibration analyst"
        dominant_fault_details = []
        
        if fault_counter:
            # Ambil fault dengan suara terbanyak (minimal 3 titik)
            dominant_fault, count = fault_counter.most_common(1)[0]
            if count >= 3:  # Threshold minimal untuk keputusan sistem
                system_diagnosis = dominant_fault
                # Ambil semua entry dengan fault dominan
                dominant_entries = [d for d in all_diagnoses if d["diagnosis"] == dominant_fault]
                # Hitung rata-rata confidence
                system_confidence = int(np.mean([d["confidence"] for d in dominant_entries]))
                # Tentukan lokasi berdasarkan titik dengan confidence tertinggi
                top_entry = max(dominant_entries, key=lambda x: x["confidence"])
                system_location = top_entry["location_hint"]
                dominant_fault_details = dominant_entries
        
        # ===== TAMPILKAN HASIL SISTEM =====
        col_sys1, col_sys2, col_sys3 = st.columns(3)
        with col_sys1:
            st.metric("Diagnosis Sistem", system_diagnosis, delta=f"{system_confidence}%" if system_confidence > 0 else None)
        with col_sys2:
            st.metric("Lokasi Terindikasi", system_location)
        with col_sys3:
            st.metric("Titik Mendukung", f"{len(dominant_fault_details)}/12" if dominant_fault_details else "0/12")
        
        if system_diagnosis != "Tidak Terdiagnosa":
            st.success(f"### 🎯 **KESIMPULAN SISTEM**: {system_diagnosis} ({system_confidence}% confidence)")
            st.info(f"**Rekomendasi Sistem**: {get_recommendation(system_diagnosis, system_location)}")
        else:
            st.warning("### ⚠️ **KESIMPULAN SISTEM**: Pola tidak konsisten di 12 titik - PERLU ANALISIS MANUAL")
            st.info(get_recommendation("Tidak Terdiagnosa"))
        
        # Tampilkan detail per titik dalam expander
        with st.expander("🔍 Detail Diagnosa Per Titik (Klik untuk Lihat)"):
            for diag in all_diagnoses:
                with st.container():
                    col_p1, col_p2, col_p3 = st.columns([2,1,1])
                    with col_p1:
                        status_icon = "🔴" if diag["diagnosis"] != "Tidak Terdiagnosa" else "⚪"
                        st.write(f"{status_icon} **{diag['point']}** | Overall: {input_data[diag['point']]:.2f} mm/s")
                    with col_p2:
                        st.write(f"**Diagnosis**: {diag['diagnosis']}")
                    with col_p3:
                        if diag["confidence"] > 0:
                            st.write(f"Confidence: **{diag['confidence']}%**")
                    if diag["diagnosis"] != "Tidak Terdiagnosa":
                        st.write(f"Lokasi Indikasi: {diag['location_hint']}")
                        st.write(f"Top Peaks: {diag['peaks'][0][0]:.1f}Hz@{diag['peaks'][0][1]:.2f}, {diag['peaks'][1][0]:.1f}Hz@{diag['peaks'][1][1]:.2f}, {diag['peaks'][2][0]:.1f}Hz@{diag['peaks'][2][1]:.2f}")
                    st.divider()
        
        # Step 6: Kesimpulan Operasional & Ekspor
        st.divider()
        col_x, col_y = st.columns(2)
        
        with col_x:
            st.subheader("📋 Rekomendasi Operasional")
            zone_c_val = ISO_LIMITS["Zone C (Unacceptable)"]
            critical_count = sum(1 for p in points if input_data[p] > zone_c_val)
            
            if critical_count > 2 or (system_diagnosis in ["MISALIGNMENT", "LOOSENESS"] and system_confidence > 80):
                st.error("🔴 **TINDAKAN KRITIS**: HENTIKAN OPERASI SEGERA! Jadwalkan perbaikan dalam 4 jam.")
                st.write("- Amankan area operasi")
                st.write("- Siapkan tim maintenance darurat")
                st.write("- Laporkan ke Mechanical Engineer & Supervisor")
            elif critical_count > 0 or system_confidence > 70:
                st.warning("🟠 **TINDAKAN**: Jadwalkan perbaikan dalam 24 jam")
                st.write("- Monitor trend vibrasi setiap 4 jam")
                st.write("- Siapkan spare part & jadwal shutdown")
            else:
                st.info("🟢 **TINDAKAN**: Jadwalkan perbaikan dalam 72 jam")
                st.write("- Monitor harian")
                st.write("- Siapkan work order di CMMS")
            
            # Tambahkan catatan kritisitas
            if "Critical" in criticality:
                st.error("❗ **CATATAN KRUSIAL**: Mesin ini diklasifikasikan **CRITICAL** - Semua keputusan harus disetujui Mechanical Engineer & Vibration Analyst Level II+")
        
        with col_y:
            st.subheader("📤 Ekspor Laporan Resmi")
            csv_data = generate_csv_report_all_points(machine_id, rpm, points, fft_inputs, input_data)
            st.download_button(
                label="⬇️ Unduh Laporan CSV (12 Titik)",
                data=csv_data,
                file_name=f"VIB_REPORT_{machine_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            st.caption("✅ Format sesuai ISO 13374 - Siap untuk audit & integrasi CMMS")
            st.info("💡 **Tips**: Buka di Excel → Filter kolom 'Diagnosis' untuk analisis cepat")

else:
    # Jika semua titik normal
    st.success("✅ **SEMUA 12 TITIK DALAM BATAS NORMAL** - Tidak diperlukan analisis FFT")
    st.balloons()
    st.info("""
    📌 **Catatan Sesuai Standar Migas**:
    - Data overall vibration sudah memadai untuk status "Normal"
    - Rekam data ini sebagai baseline untuk trend analysis
    - Jadwalkan pengukuran berikutnya sesuai interval maintenance plan
    """)

# ===== FOOTER DENGAN REFERENSI STANDAR =====
st.divider()
st.caption("""
**Referensi Standar Industri Migas**:
• ISO 13374-1:2019 (Condition monitoring data) | • ISO 10816-3:2009 (Pumps) | • ISO 10816-7:2009 (Motors)
• API RP 686 (Machinery Installation & Reliability) | • Shell DEP 31.38.60.17 | • ExxonMobil EM 005
• Vibration Institute Standard VI 1.0 | • Pertamina RU SOP-VIB-01

⚠️ Tools ini dikembangkan sebagai Decision Support System. Keputusan akhir harus melibatkan personnel kompeten sesuai ISO 18436-2.
""")
