import axios from "axios";

import client from "../client";

export type MenuCategory =
  | "메인메뉴"
  | "사이드"
  | "음료/주류"
  | "디저트"
  | "기타";

export interface OcrMenuItem {
  original_name: string;
  english_name: string;
  description: string;
  price: number;
  category?: MenuCategory;
}

export interface MenuOcrSingleResponse {
  restaurant_name?: string;
  menus: OcrMenuItem[];
}

export interface MenuOcrBatchItem {
  restaurant_name?: string;
  menus: OcrMenuItem[];
}

export interface MenuOcrBatchResponse {
  results: MenuOcrBatchItem[];
}

export interface MenuOcrPageResult {
  fileName: string;
  restaurant_name?: string;
  menus: OcrMenuItem[];
}

export const MENU_OCR_MAX_FILE_COUNT = 5;
export const MENU_OCR_MAX_FILE_SIZE = 10 * 1024 * 1024;

export const MENU_OCR_ALLOWED_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/bmp",
  "image/webp",
  "image/tiff",
] as const;

export function validateMenuOcrFiles(files: File[]): void {
  if (files.length === 0) {
    throw new Error("Please select at least one menu image.");
  }

  if (files.length > MENU_OCR_MAX_FILE_COUNT) {
    throw new Error("You can upload up to 5 menu images.");
  }

  for (const file of files) {
    if (!MENU_OCR_ALLOWED_TYPES.includes(file.type as (typeof MENU_OCR_ALLOWED_TYPES)[number])) {
      throw new Error(`${file.name}: unsupported image format.`);
    }

    if (file.size > MENU_OCR_MAX_FILE_SIZE) {
      throw new Error(`${file.name}: file size must be 10MB or less.`);
    }
  }
}

export async function ocrMenuSingle(file: File): Promise<MenuOcrSingleResponse> {
  validateMenuOcrFiles([file]);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const { data } = await client.post<MenuOcrSingleResponse>("/api/menu-ai/ocr", formData, {
      timeout: 30000,
    });

    return {
      restaurant_name: typeof data.restaurant_name === "string" ? data.restaurant_name : "",
      menus: normalizeMenus(data.menus),
    };
  } catch (error) {
    throw createMenuOcrError(error, "Menu OCR request failed.");
  }
}

export async function requestMenuOcr(files: File[]): Promise<MenuOcrPageResult[]> {
  validateMenuOcrFiles(files);

  if (files.length === 1) {
    const data = await ocrMenuSingle(files[0]);

    return [
      {
        fileName: files[0].name,
        restaurant_name: data.restaurant_name,
        menus: data.menus,
      },
    ];
  }

  const data = await requestBatchMenuOcr(files);

  return data.results.map((result, index) => ({
    fileName: files[index]?.name || `menu-${index + 1}`,
    restaurant_name: typeof result.restaurant_name === "string" ? result.restaurant_name : "",
    menus: normalizeMenus(result.menus),
  }));
}

async function requestBatchMenuOcr(files: File[]): Promise<MenuOcrBatchResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });

  try {
    const { data } = await client.post<MenuOcrBatchResponse>("/api/menu-ai/ocr/batch", formData, {
      timeout: 30000,
    });

    return {
      results: Array.isArray(data.results)
        ? data.results.map((item) => ({
            restaurant_name: typeof item.restaurant_name === "string" ? item.restaurant_name : "",
            menus: normalizeMenus(item.menus),
          }))
        : [],
    };
  } catch (error) {
    throw createMenuOcrError(error, "Batch menu OCR request failed.");
  }
}

function normalizeMenus(value: unknown): OcrMenuItem[] {
  if (!Array.isArray(value)) return [];

  return value.map((item) => {
    const menu = item as Partial<OcrMenuItem>;

    return {
      original_name: String(menu.original_name || ""),
      english_name: String(menu.english_name || ""),
      description: String(menu.description || ""),
      price: Number(menu.price || 0),
      category: normalizeCategory(menu.category),
    };
  });
}

function normalizeCategory(value: unknown): MenuCategory {
  const allowed: MenuCategory[] = ["메인메뉴", "사이드", "음료/주류", "디저트", "기타"];
  return allowed.includes(value as MenuCategory) ? (value as MenuCategory) : "기타";
}

function createMenuOcrError(error: unknown, fallback: string): Error {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    const message = extractApiErrorMessage(detail, fallback);
    const enrichedError = new Error(message) as Error & {
      response?: unknown;
      code?: string;
    };

    enrichedError.response = error.response;
    enrichedError.code = error.code;

    return enrichedError;
  }

  if (error instanceof Error) {
    return error;
  }

  return new Error(fallback);
}

function extractApiErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String(item.msg);
        }
        return JSON.stringify(item);
      })
      .join(", ");
  }

  return fallback;
}
