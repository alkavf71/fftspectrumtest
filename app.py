import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# ===== KONFIGURASI AWAL =====
ISO_LIMITS = {
    "Zone B (Acceptable)": 4.5,
    "Zone C (Unacceptable)": 7.1,
    "Zone D (Danger)": 11.0
}

# ===== FUNGSI REKOMENDASI (WAJIB ADA!) =====
def get_recommendation(diagnosis: str, point: str) -> str:
    """Return rekomendasi berdasarkan diagnosis dan lokasi"""
    rec_map = {
        "UNBALANCE": (
            "✅ **Rekomendasi**: Lakukan balancing rotor. Periksa: "
            "• Material menempel/hilang pada impeller "
            "• Korosi pada blade "
            "• Kencangkan baut rotor"
        ),
        "MISALIGNMENT": (
            "✅ **Rekomendasi**: Periksa alignment coupling. Lakukan: "
            "• Laser alignment ulang "
            "• Inspeksi kondisi coupling & spacer "
            "• Pastikan tidak ada pipe strain"
        ),
        "LOOSENESS": (
            "✅ **Rekomendasi**: Periksa kekencangan: "
            "• Baut pondasi & baseplate "
            "• Bearing housing bolts "
            "• Kondisi pondasi/crack "
            "• Lakukan torque check sesuai spec"
        ),
        "Tidak Terdiagnosa": (
            "⚠️ **Rekomendasi**: Data tidak memadai untuk diagnosa otomatis. "
            "• Lakukan analisis manual oleh vibration analyst "
            "• Periksa kualitas data pengukuran "
            "• Pertimbangkan pengukuran ulang dengan parameter lebih detail"
        )
    }
    return rec_map.get(diagnosis, rec_map["Tidak Terdiagnosa"])

# ===== FUNGSI EKSPOR CSV (AMAN TANPA DEPENDENSI) =====
def generate_csv_report(machine_id, rpm, flagged_points, fft_inputs, input_data):
    """Generate CSV report dari hasil diagnosa"""
    report_lines = []
    report_lines.append(f"Vibration Diagnostic Report - {machine_id}")
    report_lines.append(f"Tanggal: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"RPM Operasi: {rpm} | 1x RPM: {rpm/60:.2f} Hz")
    report_lines.append("\nDetail Titik Bermasalah:")
    report_lines.append("Titik,Overall (mm/s),Peak1 (Hz),Amp1 (mm/s),Peak2 (Hz),Amp2 (mm/s),Peak3 (Hz),Amp3 (mm/s),Diagnosis")
    
    rpm_hz = rpm / 60
    for point in flagged_points:
        peaks = fft_inputs.get(point, [(0,0),(0,0),(0,0)])
        # Diagnosa ulang untuk CSV
        diagnosis = "Tidak Terdiagnosa"
        for fault, rule in FAULT_RULES.items():
            # Gunakan point langsung, BUKAN session state!
            if rule["condition"](peaks, rpm_hz, point): 
                diagnosis = fault
                break
        
        report_lines.append(
            f"{point},{input_data[point]:.2f},"
            f"{peaks[0][0]:.1f},{peaks[0][1]:.2f},"
            f"{peaks[1][0]:.1f},{peaks[1][1]:.2f},"
            f"{peaks[2][0]:.1f},{peaks[2][1]:.2f},"
            f"{diagnosis}"
        )
    
    return "\n".join(report_lines)

# ===== RULE DIAGNOSA YANG DIPERBAIKI (HILANGKAN DEPENDENSI SESSION STATE!) =====
FAULT_RULES = {
    "UNBALANCE": {
        "pattern": "1x RPM dominant di radial (H/V)",
        "condition": lambda peaks, rpm_hz, point: (
            abs(peaks[0][0] - rpm_hz) < 0.05 * rpm_hz and 
            peaks[0][1] > 0.7 * sum(p[1] for p in peaks) and
            "Axial" not in point  # <-- GUNAKAN PARAMETER 'point' LANGSUNG!
        )
    },
    "MISALIGNMENT": {
        "pattern": "1x+2x RPM kuat di Axial",
        "condition": lambda peaks, rpm_hz, point: (
            "Axial" in point and  # <-- GUNAKAN PARAMETER 'point' LANGSUNG!
            any(abs(p[0] - rpm_hz) < 0.05 * rpm_hz for p in peaks[:2]) and
            any(abs(p[0] - 2 * rpm_hz) < 0.05 * rpm_hz for p in peaks[:2])
        )
    },
    "LOOSENESS": {
        "pattern": "Harmonik 1x-3x RPM dengan amplitudo menurun perlahan",
        "condition": lambda peaks, rpm_hz, point: (
            all(abs(peaks[i][0] - (i+1) * rpm_hz) < 0.05 * rpm_hz for i in range(3)) and
            peaks[1][1] > 0.5 * peaks[0][1] and 
            peaks[2][1] > 0.3 * peaks[0][1]
        )
    }
}

# ===== ANTARMUKA UTAMA =====
st.set_page_config(page_title="Vibration Diagnostic Assistant", layout="wide")
st.title("🔧 Sistem Analisis Vibrasi Pump & Motor")

# Step 1: Input Data Mesin
col1, col2 = st.columns(2)
with col1:
    machine_id = st.text_input("ID Mesin", "PUMP-01")
    rpm = st.number_input("Operating RPM", min_value=100, max_value=10000, value=1780, step=10)
    if rpm < 100:
        st.warning("⚠️ RPM minimal 100!")
    iso_zone = st.selectbox("Batas Alarm ISO", list(ISO_LIMITS.keys()), index=0)
    alarm_limit = ISO_LIMITS[iso_zone]

with col2:
    st.info(f"""
    📏 **Konfigurasi Pengukuran**  
    - Total Titik: 12 (Pump+Motor × DE/NDE × H/V/A)  
    - Batas Alarm: **{alarm_limit} mm/s** ({iso_zone})  
    - 1x RPM = {rpm/60:.1f} Hz
    """)

# Step 2: Input Overall Vibration
st.subheader("📊 Input Overall Vibration (mm/s)")
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

if flagged_points:
    st.error(f"⚠️ **{len(flagged_points)} titik melebihi batas alarm**: {', '.join(flagged_points)}")
    
    # Step 4: Tab Dinamis untuk Input FFT
    st.subheader("📈 Input FFT Spectrum untuk Titik Bermasalah")
    tabs = st.tabs(flagged_points)
    
    fft_inputs = {}
    for idx, point in enumerate(flagged_points):
        with tabs[idx]:
            st.write(f"**{point}** | Overall: {input_data[point]:.2f} mm/s")
            peaks = []
            
            for i in range(1, 4):
                col_a, col_b = st.columns(2)
                with col_a:
                    freq = st.number_input(
                        f"Peak {i} Frequency (Hz)", 
                        min_value=0.1, 
                        value=float(rpm/60 * i), 
                        key=f"{point}_freq{i}"
                    )
                with col_b:
                    amp = st.number_input(
                        f"Peak {i} Amplitude (mm/s)", 
                        min_value=0.01, 
                        value=0.5, 
                        key=f"{point}_amp{i}"
                    )
                peaks.append((freq, amp))
            
            # Visualisasi mini spektrum
            df_peaks = pd.DataFrame(peaks, columns=["Frequency (Hz)", "Amplitude (mm/s)"])
            st.bar_chart(df_peaks.set_index("Frequency (Hz)"))
            fft_inputs[point] = peaks
    
    # Step 5: Tombol Diagnosa
    if st.button("🔍 DIAGNOSA SEKARANG", type="primary", use_container_width=True):
        st.subheader("💡 Hasil Diagnosa")
        rpm_hz = rpm / 60
        
        for point, peaks in fft_inputs.items():
            diagnosis = "Tidak Terdiagnosa"
            confidence = 0
            
            # Cek semua rule (GUNAKAN 'point' LANGSUNG, BUKAN SESSION STATE!)
            for fault, rule in FAULT_RULES.items():
                if rule["condition"](peaks, rpm_hz, point):  # <-- PERBAIKAN KRUSIAL!
                    diagnosis = fault
                    confidence = min(95, 70 + int(peaks[0][1] / alarm_limit * 20))
                    break
            
            # Tampilkan hasil per titik
            with st.expander(f"✅ {point} | Overall: {input_data[point]:.2f} mm/s | **{diagnosis}** ({confidence}%)"):
                col_r, col_s = st.columns(2)
                with col_r:
                    st.metric("Dominant Frequency", f"{peaks[0][0]:.1f} Hz")
                    st.metric("1x RPM", f"{rpm_hz:.1f} Hz")
                with col_s:
                    st.write("**Top 3 Peaks:**")
                    for i, (f, a) in enumerate(peaks, 1):
                        st.write(f"• Peak {i}: {f:.1f} Hz @ {a:.2f} mm/s")
                
                if diagnosis != "Tidak Terdiagnosa":
                    st.success(f"**Kemungkinan Masalah**: {diagnosis}")
                    st.info(f"**Rekomendasi**: {get_recommendation(diagnosis, point)}")
                else:
                    st.warning("Pola tidak sesuai rulebook - perlu analisis manual oleh vibration analyst")
        
        # Step 6: Kesimpulan & Ekspor (DIPERBAIKI - CSV REAL)
        st.divider()
        col_x, col_y = st.columns(2)
        with col_x:
            st.subheader("📋 Kesimpulan Sistem")
            critical_count = sum(1 for p in flagged_points if input_data[p] > ISO_LIMITS["Zone C"])
            st.write(f"- Total titik kritis (Zone C/D): **{critical_count}**")
            if critical_count > 2:
                st.error("🔴 **Rekomendasi: Segera hentikan operasi!**")
            else:
                st.warning("🟡 **Rekomendasi: Jadwalkan perbaikan dalam 72 jam**")
        
        with col_y:
            st.subheader("📤 Ekspor Data")
            csv_data = generate_csv_report(machine_id, rpm, flagged_points, fft_inputs, input_data)
            st.download_button(
                label="⬇️ Unduh Laporan CSV",
                data=csv_data,
                file_name=f"vibration_report_{machine_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            st.info("💡 File CSV berisi semua data FFT & hasil diagnosa. Buka di Excel!")

else:
    st.success("✅ Semua titik dalam batas normal! Tidak diperlukan analisis FFT.")
    st.balloons()
