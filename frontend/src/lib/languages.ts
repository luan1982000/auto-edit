export interface LanguageOption {
  value: string;
  label: string;
}

export const SOURCE_LANGUAGES: LanguageOption[] = [
  { value: "vi", label: "Tiếng Việt" },
  { value: "en", label: "Tiếng Anh" },
  { value: "zh", label: "Tiếng Trung (Giản thể)" },
  { value: "ja", label: "Tiếng Nhật" },
  { value: "ko", label: "Tiếng Hàn" },
  { value: "th", label: "Tiếng Thái" },
  { value: "id", label: "Tiếng Indonesia" },
  { value: "ms", label: "Tiếng Mã Lai" },
  { value: "tl", label: "Tiếng Philippines" },
  { value: "fr", label: "Tiếng Pháp" },
  { value: "de", label: "Tiếng Đức" },
  { value: "es", label: "Tiếng Tây Ban Nha" },
  { value: "pt", label: "Tiếng Bồ Đào Nha" },
  { value: "it", label: "Tiếng Ý" },
  { value: "ru", label: "Tiếng Nga" },
  { value: "ar", label: "Tiếng Ả Rập" },
  { value: "hi", label: "Tiếng Hindi" },
  { value: "tr", label: "Tiếng Thổ Nhĩ Kỳ" },
  { value: "nl", label: "Tiếng Hà Lan" },
  { value: "pl", label: "Tiếng Ba Lan" },
  { value: "uk", label: "Tiếng Ukraine" },
  { value: "lo", label: "Tiếng Lào" },
  { value: "km", label: "Tiếng Khmer" },
  { value: "my", label: "Tiếng Myanmar" },
];

// Translation can also target Traditional Chinese; Whisper only has a single
// Chinese model code, so the extra variant is target-only.
export const TARGET_LANGUAGES: LanguageOption[] = [
  ...SOURCE_LANGUAGES,
  { value: "zh-Hant", label: "Tiếng Trung (Phồn thể)" },
];

export const AUTO_SOURCE_LANGUAGE = "";

export function languageLabel(
  code: string,
  options: LanguageOption[] = TARGET_LANGUAGES,
): string {
  return options.find((item) => item.value === code)?.label ?? code;
}
