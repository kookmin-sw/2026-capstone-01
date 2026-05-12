import client from "./client";

export async function detectLanguage(text: string): Promise<"ko" | "en"> {
  const res = await client.post<{ lang_code: "ko" | "en" }>("/api/translation/detect", { text });
  return res.data.lang_code;
}

export async function translateText(
  text: string,
  source: "ko" | "en",
  target: "ko" | "en"
): Promise<string> {
  const res = await client.post<{ translated_text: string }>("/api/translation/translate", {
    text,
    source,
    target,
  });
  return res.data.translated_text;
}

export async function translateToKorean(text: string): Promise<string> {
  const lang = await detectLanguage(text);
  if (lang === "ko") return text;
  return translateText(text, "en", "ko");
}
