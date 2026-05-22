import sounddevice as sd
import numpy as np
import time

def diagnose_mic():
    print("=== 🎤 AUDIO QURILMALAR RO'YXATI ===")
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        print(f"[{i}] {dev['name']} (Kirish kanallari: {dev['max_input_channels']}, Chiqish kanallari: {dev['max_output_channels']})")
    
    print("\n=== ⚙️ STANDART QURILMALAR ===")
    default_input = sd.query_devices(kind='input')
    default_output = sd.query_devices(kind='output')
    print(f"Standart kirish (Mic): {default_input['name']}")
    print(f"Standart chiqish (Speaker): {default_output['name']}")

    print("\n=== 🎙️ MIKROFONNI TEKSHIRISH (2 soniya) ===")
    print("Iltimos, mikrofonga gapiring yoki biror tovush chiqaring...")
    
    duration = 2.0  # soniya
    sample_rate = 16000
    channels = 1
    
    audio_data = []
    
    def callback(indata, frames, time, status):
        if status:
            print(f"Status: {status}", flush=True)
        audio_data.append(indata.copy())

    try:
        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype='int16',
            callback=callback
        ):
            time.sleep(duration)
        
        audio_np = np.concatenate(audio_data, axis=0)
        max_val = np.max(np.abs(audio_np))
        print(f"\nYozib olingan tovushning maksimal balandligi (Amplituda): {max_val}")
        if max_val > 100:
            print("✅ Mikrofon ishlayapti va tovushni qabul qilmoqda!")
        elif max_val > 0:
            print("⚠️ Mikrofon ulandi, lekin tovush juda past (ehtimol ovoz sozlamalarda o'chirilgan yoki pastlatilgan).")
        else:
            print("❌ Mikrofondan umuman tovush kelmayapti. Ovoz sozlamalarini tekshiring.")
            
    except Exception as e:
        print(f"\n❌ Mikrofonni ochishda xatolik yuz berdi: {e}")
        print("\nTavsiya etilgan yechimlar:")
        print("1. Tizimda pulseaudio yoki pipewire ishlayotganini tekshiring.")
        # Agarda sample_rate yoki channels mos kelmasa
        print("2. Tizim sozlamalaridan mikrofon chastotasini tekshiring (16000 Hz yoki 44100 Hz).")

if __name__ == "__main__":
    diagnose_mic()
