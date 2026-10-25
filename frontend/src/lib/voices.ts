export const TTS_VOICES = [
  { value: "vi-VN-HoaiMyNeural", label: "HoaiMy (nữ)" },
  { value: "vi-VN-NamMinhNeural", label: "NamMinh (nam)" },
] as const;

export const TTS_RATES = ["-20%", "-10%", "+0%", "+10%", "+20%"] as const;

export const TTS_RATE_LABELS: Record<string, string> = {
  "-20%": "Chậm 20%",
  "-10%": "Chậm 10%",
  "+0%": "Tự nhiên",
  "+10%": "Nhanh 10%",
  "+20%": "Nhanh 20%",
};
