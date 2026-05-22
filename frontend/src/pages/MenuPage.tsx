import { useEffect, useMemo, useRef, useState, type ChangeEvent, type CSSProperties } from "react";

import { requestMenuOcr, type MenuCategory, type MenuOcrPageResult } from "../api/auth/menuOcr";
import { translateToKorean } from "../api/translation";

interface MenuItem {
  id: number;
  sourceFileName: string;
  original: string;
  translated: string;
  description: string;
  price: number;
  visible: boolean;
  quantity: number;
  category: MenuCategory;
  tempChoice?: "HOT" | "COLD";
}

type Step = "upload" | "preview" | "loading" | "select" | "order" | "error";

const TEMP_KOREAN: Record<string, string> = {
  HOT:  "뜨거운",
  WARM: "따뜻한",
  COOL: "시원한",
  COLD: "차가운",
};
const TEMP_ENGLISH: Record<string, string> = {
  HOT:  "Hot",
  WARM: "Warm",
  COOL: "Cool",
  COLD: "Iced",
};

const CATEGORY_LABEL: Record<MenuCategory, string> = {
  "메인메뉴": "MAIN",
  사이드: "SIDE",
  "음료/주류": "DRINKS",
  디저트: "DESSERT",
  기타: "OTHER",
};

const CATEGORY_COLOR: Record<MenuCategory, { bg: string; text: string }> = {
  "메인메뉴": { bg: "var(--brand-primary-soft)", text: "#018080" },
  사이드: { bg: "#e8f5e9", text: "#2e7d32" },
  "음료/주류": { bg: "#ede7f6", text: "#5e35b1" },
  디저트: { bg: "#fce4ec", text: "#c62828" },
  기타: { bg: "#fff3e0", text: "#e65100" },
};

const CATEGORY_ORDER: MenuCategory[] = ["메인메뉴", "사이드", "음료/주류", "디저트", "기타"];

export default function MenuPage() {
  const [step, setStep] = useState<Step>("upload");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const [activePreviewIndex, setActivePreviewIndex] = useState(0);
  const [activeFileIndex, setActiveFileIndex] = useState(0);
  const [menuItems, setMenuItems] = useState<MenuItem[]>([]);
  const [restaurantName, setRestaurantName] = useState("");
  const [errorDetail, setErrorDetail] = useState("");
  const [ttsError, setTtsError] = useState("");
  const [orderNote, setOrderNote] = useState("");
  const [translatedNote, setTranslatedNote] = useState("");
  const [translatingNote, setTranslatingNote] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [koreanFullscreen, setKoreanFullscreen] = useState(false);
  const [exchangeRate, setExchangeRate] = useState<number | null>(null);
  const [partySize, setPartySize] = useState(1);
  const [showServingWarning, setShowServingWarning] = useState(false);
  const [warningFading, setWarningFading] = useState(false);

  const [activeOrderSlide, setActiveOrderSlide] = useState(0);

  const fileRef = useRef<HTMLInputElement>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const ocrRequestRef = useRef(false);
  const selectSectionRef = useRef<HTMLElement>(null);
  const carouselRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
      cancelSpeech();
    };
  }, [previewUrls]);

  // Fetch live KRW→USD rate when entering select or order screen
  useEffect(() => {
    if (step !== "order" && step !== "select") return;
    if (exchangeRate !== null) return;
    setExchangeRate(null);
    fetch("https://open.er-api.com/v6/latest/KRW")
      .then((res) => res.json())
      .then((data) => {
        if (typeof data.rates?.USD === "number") setExchangeRate(data.rates.USD);
      })
      .catch(() => {});
  }, [step]);

  const selectedItems = useMemo(
    () => menuItems.filter((item) => item.visible),
    [menuItems]
  );

  const fileNames = useMemo(() => {
    const seen = new Set<string>();
    const names: string[] = [];
    menuItems.forEach((item) => {
      if (!seen.has(item.sourceFileName)) {
        seen.add(item.sourceFileName);
        names.push(item.sourceFileName);
      }
    });
    return names;
  }, [menuItems]);

  const currentPageItems = useMemo(() => {
    const currentFile = fileNames[activeFileIndex];
    if (!currentFile) return menuItems;
    return menuItems.filter((item) => item.sourceFileName === currentFile);
  }, [menuItems, fileNames, activeFileIndex]);

  const groupedByCategory = useMemo(() => {
    const groups = new Map<MenuCategory, MenuItem[]>();
    CATEGORY_ORDER.forEach((cat) => groups.set(cat, []));
    currentPageItems.forEach((item) => groups.get(item.category)?.push(item));
    return Array.from(groups.entries()).filter(([, items]) => items.length > 0);
  }, [currentPageItems]);

  const koreanOrderMessage = useMemo(() => {
    if (!selectedItems.length) return "";
    const menuSentence = selectedItems
      .map((item) => {
        const baseName = item.original
          .replace(/\s*\(HOT[\s/]*ICE\)/gi, "")
          .replace(/\s*\(ICE[\s/]*HOT\)/gi, "")
          .trim();
        const prefix = item.tempChoice ? `${TEMP_KOREAN[item.tempChoice]} ` : "";
        return `${prefix}${baseName} ${toKoreanCount(item.quantity)}`;
      })
      .join(", ");
    const partySuffix = partySize === 1
      ? " 혼자 먹을 거예요."
      : ` ${partySize}명이서 먹을게요.`;
    const base = `사장님 여기 ${menuSentence} 주세요.${partySuffix}`;
    const noteInKorean = translatedNote.trim();
    return noteInKorean ? `${base}\n\n${noteInKorean}` : base;
  }, [translatedNote, selectedItems, partySize]);

  const englishOrderMessage = useMemo(() => {
    if (!selectedItems.length) return "";
    const items = selectedItems
      .map((item) => {
        const baseName = item.translated
          .replace(/\s*\(HOT[\s/]*ICE\)/gi, "")
          .replace(/\s*\(ICE[\s/]*HOT\)/gi, "")
          .trim();
        const prefix = item.tempChoice ? `${TEMP_ENGLISH[item.tempChoice]} ` : "";
        const qty = item.quantity > 1 ? ` ×${item.quantity}` : "";
        return `${prefix}${baseName}${qty}`;
      })
      .join(", ");
    const partySuffix = partySize > 1 ? ` We are a party of ${partySize}.` : "";
    const base = `Excuse me, I'd like to order ${items}.${partySuffix}`;
    const note = orderNote.trim();
    return note ? `${base}\n${note}` : base;
  }, [selectedItems, partySize, orderNote]);

  const totalKRW = useMemo(
    () => selectedItems.reduce((sum, item) => sum + item.price * item.quantity, 0),
    [selectedItems]
  );

  useEffect(() => {
    // 선택된 아이템이 있고, 그 중 하나라도 quantity < partySize일 때만 경고
    const needsWarning =
      partySize >= 2 &&
      selectedItems.length > 0 &&
      selectedItems.some((item) => item.quantity < partySize);

    if (!needsWarning) {
      setShowServingWarning(false);
      setWarningFading(false);
      return;
    }
    setShowServingWarning(true);
    setWarningFading(false);
    const t1 = setTimeout(() => setWarningFading(true), 7000);
    const t2 = setTimeout(() => { setShowServingWarning(false); setWarningFading(false); }, 8000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [partySize, selectedItems]);

  const totalUSD = useMemo(() => {
    if (!exchangeRate || totalKRW === 0) return null;
    return (totalKRW * exchangeRate).toFixed(2);
  }, [exchangeRate, totalKRW]);

  const handleOpenPicker = () => fileRef.current?.click();

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;

    const mergedFiles = [...selectedFiles, ...files].slice(0, 5);
    previewUrls.forEach((url) => URL.revokeObjectURL(url));

    setSelectedFiles(mergedFiles);
    setPreviewUrls(mergedFiles.map((file) => URL.createObjectURL(file)));
    setActivePreviewIndex(0);
    setErrorDetail("");
    setStep("preview");

    if (fileRef.current) fileRef.current.value = "";
  };

  const handleRemovePreview = (index: number) => {
    const nextFiles = selectedFiles.filter((_, idx) => idx !== index);
    const nextUrls = previewUrls.filter((_, idx) => idx !== index);

    const removedUrl = previewUrls[index];
    if (removedUrl) URL.revokeObjectURL(removedUrl);

    setSelectedFiles(nextFiles);
    setPreviewUrls(nextUrls);
    setActivePreviewIndex((prev) => (nextFiles.length === 0 ? 0 : Math.min(prev, nextFiles.length - 1)));
    setStep(nextFiles.length ? "preview" : "upload");
  };

  const handleTranslate = async () => {
    if (!selectedFiles.length || ocrRequestRef.current) return;

    ocrRequestRef.current = true;
    setStep("loading");
    setErrorDetail("");

    try {
      const response = await requestMenuOcr(selectedFiles);
      const nextMenuItems = mapResultsToMenuItems(response);

      setRestaurantName(response[0]?.restaurant_name || "");
      setMenuItems(nextMenuItems);
      setActiveFileIndex(0);
      setActivePreviewIndex(0);
      setStep("select");
    } catch (error: unknown) {
      const err = error as {
        code?: string;
        message?: string;
        response?: { status?: number; data?: { message?: string; detail?: string } };
      };

      const status = err.response?.status;
      const message = err.response?.data?.message || err.response?.data?.detail || err.message || "";

      if (err.code === "ECONNABORTED") {
        setErrorDetail("The request timed out. Please try again.");
      } else if (status === 401) {
        setErrorDetail("Authorization failed (401).");
      } else if (status === 413) {
        setErrorDetail("The selected file is too large (413).");
      } else if (status) {
        setErrorDetail(`Server error ${status}${message ? `: ${message}` : ""}`);
      } else {
        setErrorDetail(message || "An unknown error occurred.");
      }

      setStep("error");
    } finally {
      ocrRequestRef.current = false;
    }
  };

  const handleReset = () => {
    previewUrls.forEach((url) => URL.revokeObjectURL(url));
    setSelectedFiles([]);
    setPreviewUrls([]);
    setActivePreviewIndex(0);
    setActiveFileIndex(0);
    setMenuItems([]);
    setRestaurantName("");
    setErrorDetail("");
    setTtsError("");
    setOrderNote("");
    setTranslatedNote("");
    setTranslatingNote(false);
    setEditingNote(false);
    setSpeaking(false);
    setKoreanFullscreen(false);
    setExchangeRate(null);
    setPartySize(1);
    setStep("upload");
    cancelSpeech();
    utteranceRef.current = null;
  };

  const toggleItem = (id: number) => {
    setMenuItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, visible: !item.visible } : item))
    );
  };

  const updateQuantity = (id: number, delta: number) => {
    setMenuItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, quantity: Math.max(1, item.quantity + delta) } : item
      )
    );
  };

  const setTempChoice = (id: number, temp: "HOT" | "COLD") => {
    setMenuItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, tempChoice: temp } : item))
    );
  };

  const allCurrentSelected = useMemo(
    () => currentPageItems.length > 0 && currentPageItems.every((item) => item.visible),
    [currentPageItems]
  );

  const handleToggleAll = () => {
    const nextVisible = !allCurrentSelected;
    const currentFileIds = new Set(currentPageItems.map((item) => item.id));
    setMenuItems((prev) =>
      prev.map((item) =>
        currentFileIds.has(item.id) ? { ...item, visible: nextVisible } : item
      )
    );
  };

  const goToOrderSlide = (index: number) => {
    const el = carouselRef.current;
    if (!el) return;
    el.scrollTo({ left: el.offsetWidth * index, behavior: "smooth" });
    setActiveOrderSlide(index);
  };

  const handleGoToOrder = () => {
    if (!selectedItems.length) return;
    setEditingNote(false);
    setActiveOrderSlide(0);
    setStep("order");
  };

  const handleSaveNote = async () => {
    const note = orderNote.trim();
    if (!note) { setTranslatedNote(""); setEditingNote(false); return; }
    setTranslatingNote(true);
    try {
      const raw = await translateToKorean(note);
      setTranslatedNote(makePolite(raw));
    } catch (err) {
      console.error("[translation] failed:", err);
      setTranslatedNote("");
    } finally {
      setTranslatingNote(false);
      setEditingNote(false);
    }
  };

  const handleSpeak = () => {
    // Stop if already playing
    if (speaking) {
      cancelSpeech();
      setSpeaking(false);
      utteranceRef.current = null;
      return;
    }
    if (!koreanOrderMessage.trim()) return;

    const SpeechSynthesisUtteranceCtor = getSpeechSynthesisUtterance();
    const speechSynthesis = getSpeechSynthesis();
    if (!SpeechSynthesisUtteranceCtor || !speechSynthesis) {
      setTtsError("Text-to-speech is not supported on this device.");
      return;
    }
    setTtsError("");

    const utterance = new SpeechSynthesisUtteranceCtor(koreanOrderMessage);
    utterance.lang = "ko-KR";
    utterance.rate = 0.88;   // slightly slower for clarity
    utterance.pitch = 1.0;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => { setSpeaking(false); utteranceRef.current = null; };
    utterance.onerror = () => {
      setSpeaking(false);
      utteranceRef.current = null;
      setTtsError("Could not play text-to-speech. Please show the Korean text instead.");
    };
    utteranceRef.current = utterance;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  };

  const handleBackButton = () => {
    if (step === "upload") return;
    if (step === "order") { setEditingNote(false); setStep("select"); }
    else handleReset();
  };

  const handlePageTabClick = (index: number) => {
    setActiveFileIndex(index);
    setActivePreviewIndex(index);
  };

  const activeFileIndexRef = useRef(activeFileIndex);
  const fileNamesRef = useRef(fileNames);
  useEffect(() => { activeFileIndexRef.current = activeFileIndex; }, [activeFileIndex]);
  useEffect(() => { fileNamesRef.current = fileNames; }, [fileNames]);

  useEffect(() => {
    if (step !== "select") return;
    const el = selectSectionRef.current;
    if (!el) return;

    let startX = 0;
    let startY = 0;
    let isHorizontal = false;

    const onStart = (e: TouchEvent) => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      isHorizontal = false;
    };

    const onMove = (e: TouchEvent) => {
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
        isHorizontal = Math.abs(dx) > Math.abs(dy);
      }
      if (isHorizontal) e.preventDefault();
    };

    const onEnd = (e: TouchEvent) => {
      const dx = e.changedTouches[0].clientX - startX;
      const dy = e.changedTouches[0].clientY - startY;
      isHorizontal = false;
      if (Math.abs(dx) < 50 || Math.abs(dx) <= Math.abs(dy)) return;

      const current = activeFileIndexRef.current;
      const total = fileNamesRef.current.length;
      if (dx < 0 && current < total - 1) handlePageTabClick(current + 1);
      else if (dx > 0 && current > 0) handlePageTabClick(current - 1);
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: false });
    el.addEventListener("touchend", onEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
    };
  }, [step]);

  return (
    <div style={styles.page}>
      <style>{`
        @keyframes menuBounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.35; }
          40% { transform: translateY(-7px); opacity: 1; }
        }
        .order-carousel::-webkit-scrollbar { display: none; }
      `}</style>

      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp,image/bmp,image/tiff"
        multiple
        onChange={handleFileChange}
        style={styles.hiddenInput}
      />

      <div style={styles.phone}>
        <header style={styles.header}>
          <button
            type="button"
            onClick={step === "upload" ? undefined : handleBackButton}
            style={{ ...styles.backButton, ...(step === "upload" ? styles.backButtonHidden : null) }}
            aria-label="Go back"
          >
            <svg width="20" height="20" viewBox="0 0 64 64" fill="none" aria-hidden="true">
              <path d="M37.3334 42.6673L26.6667 32.0007L37.3334 21.334" stroke="currentColor" strokeWidth="5.33333" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <h1 style={styles.headerTitle}>Menu Order Helper</h1>
          <div style={styles.headerSpacer} />
        </header>

        {/* ── Upload ── */}
        {step === "upload" ? (
          <section style={styles.uploadSection}>
            <h2 style={styles.uploadTitle}>Take a photo of the menu to start ordering</h2>
            <p style={styles.uploadSubtitle}>
              We'll translate the menu and prepare your order so you can show it at the restaurant.
            </p>
            <button type="button" onClick={handleOpenPicker} style={styles.uploadBox}>
              <div style={styles.plusButton}>
                <img src="/icon-plus.svg" alt="Add" style={{ width: 28, height: 28, display: "block", filter: "brightness(0) invert(1)" }} />
              </div>
              <p style={styles.uploadCopy}>Add Menu Photo</p>
            </button>
            <button type="button" disabled style={styles.translateButtonDisabled}>
              Start Ordering
            </button>
          </section>
        ) : null}

        {/* ── Preview ── */}
        {step === "preview" ? (
          <section style={styles.previewSection}>
            <h2 style={styles.previewTitle}>MENU</h2>
            <p style={styles.previewSubtitle}>Menu photo added</p>
            <div style={styles.previewDivider} />

            <div style={{ ...styles.previewMainFrame, position: "relative" }}>
              {previewUrls[activePreviewIndex] ? (
                <img
                  src={previewUrls[activePreviewIndex]}
                  alt=""
                  style={styles.previewLargeImage}
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
              ) : null}
              <button
                type="button"
                onClick={() => handleRemovePreview(activePreviewIndex)}
                style={styles.previewXOverlay}
                aria-label="Remove image"
              >
                <svg width="12" height="12" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                  <path d="M16 16L48 48M48 16L16 48" stroke="currentColor" strokeWidth="7" strokeLinecap="round"/>
                </svg>
              </button>
            </div>

            <div style={styles.previewRail}>
              {previewUrls.map((url, index) => (
                  <div
                    key={`${url}-${index}`}
                    style={{
                      ...styles.previewThumbWrap,
                      ...(activePreviewIndex === index ? styles.previewThumbWrapActive : null),
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => setActivePreviewIndex(index)}
                      style={styles.previewThumbButton}
                    >
                      <img src={url} alt="" style={styles.previewThumb} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRemovePreview(index)}
                      style={styles.previewRemoveButton}
                      aria-label="Remove image"
                    >
                      <svg width="8" height="8" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                        <path d="M16 16L48 48M48 16L16 48" stroke="currentColor" strokeWidth="9" strokeLinecap="round"/>
                      </svg>
                    </button>
                  </div>
                ))}
              {previewUrls.length < 5 ? (
                <button type="button" onClick={handleOpenPicker} style={styles.addMoreThumb}>+</button>
              ) : null}
            </div>

            <button type="button" onClick={handleTranslate} style={styles.translateButton}>
              Start Ordering{selectedFiles.length > 1 ? ` (${selectedFiles.length} Photos)` : ""}
            </button>
          </section>
        ) : null}

        {/* ── Loading ── */}
        {step === "loading" ? (
          <section style={styles.loadingSection}>
            <div style={styles.loadingDots}>
              <span style={{ ...styles.loadingDot, animationDelay: "0s" }} />
              <span style={{ ...styles.loadingDot, animationDelay: "0.15s" }} />
              <span style={{ ...styles.loadingDot, animationDelay: "0.3s" }} />
              <span style={{ ...styles.loadingDot, animationDelay: "0.45s" }} />
            </div>
            <p style={styles.loadingText}>Preparing your menu</p>
          </section>
        ) : null}

        {/* ── Select ── */}
        {step === "select" ? (
          <section ref={selectSectionRef} style={styles.selectSection}>
            {/* Fixed: photo + page tabs */}
            <div style={styles.stickyHero}>
              {/* Select All (left) + Party size counter (right) */}
              <div style={styles.partySizeRow}>
                <button
                  type="button"
                  onClick={handleToggleAll}
                  style={{
                    ...styles.selectAllBtn,
                    ...(allCurrentSelected ? styles.selectAllBtnActive : null),
                  }}
                >
                  {allCurrentSelected ? "Deselect All" : "Select All"}
                </button>
                <div style={styles.partySizeControls}>
                  <span style={styles.partySizeLabel}>Guests</span>
                  <button
                    type="button"
                    onClick={() => setPartySize((n) => Math.max(1, n - 1))}
                    style={styles.partySizeBtn}
                    disabled={partySize <= 1}
                  >−</button>
                  <span style={styles.partySizeCount}>{partySize}</span>
                  <button
                    type="button"
                    onClick={() => setPartySize((n) => n + 1)}
                    style={styles.partySizeBtn}
                  >+</button>
                </div>
              </div>


              {fileNames.length > 1 ? (
                <div style={styles.pageTabRail}>
                  {fileNames.map((_, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => handlePageTabClick(index)}
                      style={{
                        ...styles.pageTab,
                        ...(activeFileIndex === index ? styles.pageTabActive : null),
                      }}
                    >
                      Page {index + 1}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            {/* Scrollable: category-grouped menu items */}
            <div style={styles.menuList}>
              {restaurantName ? <p style={styles.restaurantText}>{restaurantName}</p> : null}

              {groupedByCategory.map(([category, items]) => {
                const color = CATEGORY_COLOR[category];
                return (
                  <div key={category} style={styles.categoryGroup}>
                    <div style={styles.categoryHeader}>
                      <span style={{
                        ...styles.categoryBadge,
                        background: color.bg,
                        color: color.text,
                      }}>
                        {CATEGORY_LABEL[category]}
                      </span>
                    </div>

                    {items.map((item) => {
                      return (
                        <article
                          key={item.id}
                          style={{
                            ...styles.menuCard,
                            ...(item.visible ? styles.menuCardSelected : styles.menuCardDimmed),
                          }}
                        >
                          {/* Row 1: 제목(좌) + 토글(우) */}
                          <div style={styles.menuTitleRow}>
                            <p style={{ ...styles.menuTitle, fontWeight: item.visible ? 800 : 500 }}>
                              {item.translated}
                            </p>
                            <button
                              type="button"
                              onClick={() => toggleItem(item.id)}
                              style={{ ...styles.toggle, ...(item.visible ? styles.toggleOn : styles.toggleOff), flexShrink: 0 }}
                              aria-label={item.visible ? "Disable item" : "Enable item"}
                            >
                              <span style={{ ...styles.toggleThumb, ...(item.visible ? styles.toggleThumbOn : styles.toggleThumbOff) }} />
                            </button>
                          </div>

                          {/* Row 2: 한글 원문(좌) + 가격(우) */}
                          <div style={styles.menuMetaRow}>
                            <span style={styles.menuMeta}>{item.original}</span>
                            {item.price > 0 ? (
                              <span style={{
                                ...styles.menuPriceInline,
                                color: item.visible ? "var(--brand-primary)" : "var(--neutral-500)",
                              }}>
                                {item.price.toLocaleString()}원
                                {exchangeRate && item.visible ? (
                                  <span style={styles.usdPill}>
                                    &nbsp;≈&nbsp;${(item.price * item.quantity * exchangeRate).toFixed(2)}
                                  </span>
                                ) : null}
                              </span>
                            ) : null}
                          </div>

                          {/* 설명 */}
                          <p style={styles.menuDescription}>{item.description}</p>

                          {/* 수량 */}
                          {item.visible ? (
                            <div style={styles.quantityRow}>
                              <button
                                type="button"
                                onClick={() => updateQuantity(item.id, -1)}
                                disabled={item.quantity <= 1}
                                style={{ ...styles.quantityBtn, opacity: item.quantity <= 1 ? 0.35 : 1 }}
                              >−</button>
                              <span style={styles.quantityCount}>{item.quantity} serving{item.quantity > 1 ? "s" : ""}</span>
                              <button type="button" onClick={() => updateQuantity(item.id, 1)} style={styles.quantityBtn}>+</button>
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                );
              })}
            </div>

            {showServingWarning ? (
              <div style={{
                ...styles.servingWarning,
                opacity: warningFading ? 0 : 1,
                transition: warningFading ? "opacity 1s ease" : "opacity 0.25s ease",
              }}>
                Some items may require a minimum order of 2 or 3 servings. Please confirm with the restaurant staff before ordering.
              </div>
            ) : null}

            <div style={styles.bottomBar}>
              {selectedItems.length > 0 && totalKRW > 0 ? (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, padding: "0 4px" }}>
                  <span style={{ fontSize: "0.8rem", color: "var(--neutral-500)", fontWeight: 700 }}>{selectedItems.length} item{selectedItems.length > 1 ? "s" : ""} selected</span>
                  <span style={{ fontSize: "0.95rem", fontWeight: 900, color: "var(--neutral-900)" }}>₩{totalKRW.toLocaleString()}</span>
                </div>
              ) : null}
              <button
                type="button"
                onClick={handleGoToOrder}
                disabled={!selectedItems.length}
                style={{
                  ...styles.orderButton,
                  ...(!selectedItems.length ? styles.orderButtonDisabled : null),
                }}
              >
                {selectedItems.length > 0 ? `Order (${selectedItems.length})` : "Select items to order"}
              </button>
            </div>
          </section>
        ) : null}

        {/* ── Order ── */}
        {step === "order" ? (
          <section style={styles.orderSection}>
            {/* 1. Item review cards with next-button navigation */}
            <div style={{ position: "relative", flexShrink: 0 }}>
            <div ref={carouselRef} style={styles.orderCarousel} className="order-carousel"
              onScroll={(e) => {
                const el = e.currentTarget;
                const idx = Math.round(el.scrollLeft / el.offsetWidth);
                setActiveOrderSlide(idx);
              }}
            >
              {selectedItems.map((item, idx) => (
                <div key={item.id} style={styles.orderSlide}>
                  <div style={styles.orderSlideCard}>
                    <span style={styles.orderSlideCounter}>{idx + 1} / {selectedItems.length}</span>
                    <p style={styles.orderSlideName}>{item.translated}</p>
                    <p style={styles.orderSlideOriginal}>{item.original}</p>
                    <div style={styles.orderSlideRow}>
                      {item.quantity > 1 ? (
                        <span style={styles.orderQtyBadge}>×{item.quantity}</span>
                      ) : null}
                      {item.price > 0 ? (
                        <span style={styles.orderPriceHint}>
                          {(item.price * item.quantity).toLocaleString()}원
                          {exchangeRate ? (
                            <span style={styles.orderUsdHint}> · ${(item.price * item.quantity * exchangeRate).toFixed(2)}</span>
                          ) : null}
                        </span>
                      ) : null}
                    </div>

                    {/* Temperature selector — HOT / COLD only */}
                    <div style={styles.slideTempRow}>
                      {(["HOT", "COLD"] as const).map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => setTempChoice(item.id, t)}
                          style={{
                            ...styles.slideTempBtn,
                            ...(item.tempChoice === t
                              ? (t === "HOT" ? styles.slideTempBtnHot : styles.slideTempBtnCold)
                              : null),
                          }}
                        >{t}</button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {/* < prev button — 2번째 슬라이드부터 표시 */}
            {activeOrderSlide > 0 ? (
              <button
                type="button"
                onClick={() => goToOrderSlide(activeOrderSlide - 1)}
                style={styles.carouselPrevBtn}
                aria-label="Previous item"
              >
                <svg width="9" height="15" viewBox="0 0 9 15" fill="none" aria-hidden="true">
                  <path d="M8 1L1 7.5L8 14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            ) : null}

            {/* > next button — 마지막 슬라이드 전까지 표시 */}
            {activeOrderSlide < selectedItems.length - 1 ? (
              <button
                type="button"
                onClick={() => goToOrderSlide(activeOrderSlide + 1)}
                style={styles.carouselNextBtn}
                aria-label="Next item"
              >
                <svg width="9" height="15" viewBox="0 0 9 15" fill="none" aria-hidden="true">
                  <path d="M1 1L8 7.5L1 14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            ) : null}
            </div>

            {/* 2. English message + special request (combined) */}
            {!editingNote ? (
              /* Closed: dashed toggle button */
              <button
                type="button"
                onClick={() => setEditingNote(true)}
                style={{
                  ...styles.noteToggleBtn,
                  color: orderNote.trim() ? "var(--neutral-800)" : "var(--neutral-500)",
                  fontWeight: orderNote.trim() ? 600 : 400,
                }}
              >
                {orderNote.trim()
                  ? <><span style={{ marginRight: 6, fontSize: "0.9rem" }}>🖊</span>{orderNote}</>
                  : "+ Add special request"}
              </button>
            ) : (
              /* Open: English message shown inside the box, then textarea */
              <div style={styles.noteExpandedBox}>
                <p style={styles.englishMessage}>{englishOrderMessage}</p>
                <div style={styles.noteBoxDivider} />
                <div style={{ position: "relative" }}>
                  <textarea
                    value={orderNote}
                    onChange={(e) => { setOrderNote(e.target.value); setTranslatedNote(""); }}
                    placeholder="Any special requests? (e.g. no spicy, extra napkins)"
                    style={styles.noteTextarea}
                    rows={2}
                    autoFocus
                  />
                  <button
                    type="button"
                    disabled={translatingNote}
                    onClick={handleSaveNote}
                    style={styles.textareaEnterBtn}
                    aria-label="Save"
                  >
                    {translatingNote ? (
                      <span style={{ fontSize: "0.6rem", letterSpacing: 1 }}>···</span>
                    ) : (
                      <svg width="14" height="12" viewBox="0 0 14 12" fill="none">
                        <path d="M13 1V5a2 2 0 0 1-2 2H1m0 0 4-4M1 7l4 4" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* 3. Info row */}
            <div style={styles.infoRow}>
              <span style={styles.infoIcon}>i</span>
              <span style={styles.infoText}>Please show this screen to the staff.</span>
            </div>

            {/* 4. Korean card — for restaurant staff */}
            <div style={styles.koreanCard}>
              <p style={styles.koreanMessage}>{koreanOrderMessage}</p>
              <div style={styles.koreanActions}>
                <button
                  type="button"
                  onClick={() => setKoreanFullscreen(true)}
                  style={styles.koreanIconButton}
                  aria-label="Fullscreen"
                >
                  <svg width="18" height="18" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                    <path d="M26.6666 50.6663H13.3333V37.333M37.3333 13.333H50.6666V26.6663" stroke="#374151" strokeWidth="5.33333" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={handleSpeak}
                  style={styles.koreanIconButton}
                  aria-label={speaking ? "Stop" : "Play TTS"}
                >
                  {speaking ? (
                    <svg width="18" height="18" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                      <path d="M21.3333 18.6667V45.3333" stroke="#374151" strokeWidth="10.6667" strokeLinecap="round"/>
                      <path d="M42.6667 18.6667V45.3333" stroke="#374151" strokeWidth="10.6667" strokeLinecap="round"/>
                    </svg>
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                      <path d="M12 25.3333H22.6667L36 14.6667V49.3333L22.6667 38.6667H12V25.3333Z" stroke="#374151" strokeWidth="5.33333" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M43 25.3333C46.6667 29.3333 46.6667 34.6667 43 38.6667M49 20C55.3333 26.6667 55.3333 37.3333 49 44" stroke="#374151" strokeWidth="5.33333" strokeLinecap="round"/>
                    </svg>
                  )}
                </button>
              </div>
            </div>
            {ttsError ? <p style={styles.errorBody}>{ttsError}</p> : null}

            {/* 5. USD conversion card */}
            {totalKRW > 0 ? (
              <div style={styles.usdCard}>
                <div style={styles.usdRow}>
                  <span style={styles.usdLabel}>Estimated Total</span>
                  <div style={styles.usdAmounts}>
                    <span style={styles.krwText}>₩{totalKRW.toLocaleString()}</span>
                    {totalUSD ? (
                      <span style={styles.usdText}>≈ ${totalUSD} <span style={styles.usdCurrency}>USD</span></span>
                    ) : (
                      <span style={styles.usdLoading}>Fetching rate…</span>
                    )}
                  </div>
                </div>
                {exchangeRate ? (
                  <p style={styles.usdDisclaimer}>
                    1 USD ≈ ₩{Math.round(1 / exchangeRate).toLocaleString()} · Live rate · For reference only
                  </p>
                ) : null}
              </div>
            ) : null}

            <button type="button" onClick={() => setStep("select")} style={styles.doneButton}>
              Done
            </button>
          </section>
        ) : null}

        {/* ── Korean fullscreen overlay ── */}
        {koreanFullscreen ? (
          <div style={styles.fullscreenOverlay}>
            <div style={styles.fullscreenHeader}>
              <p style={styles.fullscreenLabel}>사장님께 보여주세요</p>
              <button
                type="button"
                onClick={() => setKoreanFullscreen(false)}
                style={styles.fullscreenClose}
                aria-label="Close"
              >
                <svg width="16" height="16" viewBox="0 0 64 64" fill="none" aria-hidden="true">
                  <path d="M16 16L48 48M48 16L16 48" stroke="currentColor" strokeWidth="7" strokeLinecap="round"/>
                </svg>
              </button>
            </div>
            <p style={styles.fullscreenText}>{koreanOrderMessage}</p>
            <div style={styles.fullscreenFooter}>
              <button type="button" onClick={handleSpeak} style={styles.fullscreenSpeakBtn}>
                <svg width="22" height="22" viewBox="0 0 64 64" fill="none" style={{ flexShrink: 0 }} aria-hidden="true">
                  {speaking ? (
                    <>
                      <path d="M21.3333 18.6667V45.3333" stroke="currentColor" strokeWidth="10.6667" strokeLinecap="round"/>
                      <path d="M42.6667 18.6667V45.3333" stroke="currentColor" strokeWidth="10.6667" strokeLinecap="round"/>
                    </>
                  ) : (
                    <>
                      <path d="M12 25.3333H22.6667L36 14.6667V49.3333L22.6667 38.6667H12V25.3333Z" stroke="currentColor" strokeWidth="5.33333" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M43 25.3333C46.6667 29.3333 46.6667 34.6667 43 38.6667M49 20C55.3333 26.6667 55.3333 37.3333 49 44" stroke="currentColor" strokeWidth="5.33333" strokeLinecap="round"/>
                    </>
                  )}
                </svg>
                {speaking ? "Stop" : "Read aloud"}
              </button>
            </div>
          </div>
        ) : null}

        {/* ── Error ── */}
        {step === "error" ? (
          <section style={styles.errorSection}>
            <p style={styles.errorTitle}>We could not translate this menu.</p>
            <p style={styles.errorBody}>{errorDetail || "Please try again with another image."}</p>
            <button type="button" onClick={handleReset} style={styles.translateButton}>
              Start Over
            </button>
          </section>
        ) : null}
      </div>
    </div>
  );
}

function toKoreanCount(n: number): string {
  const words = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉", "열",
    "열하나", "열둘", "열셋", "열넷", "열다섯", "열여섯", "열일곱", "열여덟", "열아홉", "스물"];
  return n > 0 && n < words.length ? words[n] : `${n}개`;
}

function makePolite(korean: string): string {
  const text = korean.trim();
  if (!text) return text;
  const politeEndings = ["주세요", "해주세요", "부탁드립니다", "드립니다", "습니다", "ㅂ니다", "겠어요", "할게요", "예요", "이에요", "아요", "어요"];
  if (politeEndings.some((e) => text.endsWith(e))) return text;
  return `${text} 부탁드립니다`;
}

function normalizePrice(raw: number): number {
  // Korean menus sometimes write ₩17,000 as "17.0" → OCR returns 17.0
  // Any price under ₩1,000 is unrealistic for a restaurant item
  if (raw > 0 && raw < 1000) return Math.round(raw * 1000);
  return raw;
}

function mapResultsToMenuItems(results: MenuOcrPageResult[]): MenuItem[] {
  let nextId = 1;
  return results.flatMap((result) =>
    result.menus.map((menu, index) => ({
      id: nextId++,
      sourceFileName: result.fileName,
      original: menu.original_name,
      translated: menu.english_name,
      description: menu.description,
      price: normalizePrice(menu.price),
      visible: false,
      quantity: 1,
      category: menu.category ?? "기타",
    }))
  );
}

function getSpeechSynthesis(): SpeechSynthesis | null {
  if (typeof window === "undefined") return null;
  return window.speechSynthesis ?? null;
}

function getSpeechSynthesisUtterance(): typeof SpeechSynthesisUtterance | null {
  if (typeof window === "undefined") return null;
  return typeof window.SpeechSynthesisUtterance === "function"
    ? window.SpeechSynthesisUtterance
    : null;
}

function cancelSpeech(): void {
  try {
    getSpeechSynthesis()?.cancel();
  } catch {
    // Android WebView can expose partial Web Speech support. Leaving the page
    // should never break route transitions if speech cleanup fails.
  }
}


const styles: Record<string, CSSProperties> = {
  page: {
    height: "calc(var(--app-viewport-height) - var(--app-bottom-nav-reserved))",
    background: "var(--surface-muted)",
    display: "flex",
    flexDirection: "column",
    fontFamily: "var(--app-font-family)",
    overflowX: "hidden",
  },
  hiddenInput: { display: "none" },
  phone: {
    flex: 1,
    width: "100%",
    minHeight: 0,
    background: "var(--surface-muted)",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    position: "relative",
  },

  /* ── Header ── */
  header: {
    display: "grid",
    gridTemplateColumns: "44px 1fr 44px",
    alignItems: "center",
    minHeight: 52,
    padding: "calc(var(--app-safe-top) + 10px) 16px 10px",
    flexShrink: 0,
    background: "var(--surface-panel)",
    borderBottom: "1px solid #e5e7eb",
  },
  backButton: {
    border: "none",
    background: "transparent",
    color: "var(--neutral-800)",
    cursor: "pointer",
    padding: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  backButtonHidden: { visibility: "hidden", cursor: "default" },
  headerTitle: {
    margin: 0,
    textAlign: "center",
    fontSize: "1rem",
    fontWeight: 900,
    color: "var(--neutral-900)",
    letterSpacing: "-0.025em",
  },
  headerSpacer: { width: 44 },

  /* ── Upload ── */
  uploadSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "36px 24px 24px",
    overflowY: "auto",
    background: "var(--surface-panel)",
  },
  uploadTitle: {
    margin: "0 0 10px",
    fontSize: "1.4rem",
    fontWeight: 900,
    color: "var(--neutral-900)",
    textAlign: "center",
    lineHeight: 1.25,
    letterSpacing: "-0.03em",
  },
  uploadSubtitle: {
    margin: "0 0 28px",
    fontSize: "0.84rem",
    color: "var(--neutral-500)",
    textAlign: "center",
    lineHeight: 1.65,
    maxWidth: 260,
  },
  uploadBox: {
    flex: 1,
    width: "100%",
    minHeight: 180,
    borderRadius: 24,
    border: "2px dashed #c8bfb5",
    background: "#fdfaf5",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    cursor: "pointer",
    marginBottom: 16,
  },
  plusButton: {
    width: 64,
    height: 64,
    borderRadius: 20,
    background: "var(--brand-primary)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  uploadCopy: { margin: 0, color: "var(--neutral-600)", fontSize: "0.88rem", fontWeight: 700 },
  translateButton: {
    width: "100%",
    marginTop: "auto",
    border: "none",
    borderRadius: 16,
    height: 54,
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontSize: "1rem",
    fontWeight: 900,
    cursor: "pointer",
    letterSpacing: "-0.01em",
  },
  translateButtonDisabled: {
    width: "100%",
    border: "none",
    borderRadius: 16,
    height: 54,
    background: "#f3f4f6",
    color: "var(--neutral-400)",
    fontSize: "1rem",
    fontWeight: 700,
    cursor: "not-allowed",
    letterSpacing: "-0.01em",
  },

  /* ── Preview ── */
  previewSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "20px 16px 16px",
    gap: 8,
    overflowY: "auto",
    background: "#fdfaf5",
  },
  previewTitle: {
    margin: 0,
    fontSize: "2rem",
    fontWeight: 900,
    color: "var(--neutral-900)",
    letterSpacing: "-0.02em",
    textAlign: "center" as CSSProperties["textAlign"],
  },
  previewSubtitle: {
    margin: 0,
    fontSize: "0.84rem",
    fontWeight: 500,
    color: "var(--neutral-500)",
    textAlign: "center" as CSSProperties["textAlign"],
  },
  previewDivider: {
    width: 56,
    height: 1,
    background: "var(--neutral-400)",
    margin: "4px 0 8px",
    flexShrink: 0,
  },
  previewMainFrame: {
    width: "100%",
    height: 320,
    borderRadius: 18,
    background: "var(--border-soft)",
    overflow: "hidden",
    flexShrink: 0,
  },
  previewLargeImage: { width: "100%", height: "100%", objectFit: "cover" },
  previewXOverlay: {
    position: "absolute",
    top: 10,
    right: 10,
    width: 30,
    height: 30,
    borderRadius: 8,
    border: "none",
    background: "rgba(17,24,39,0.6)",
    color: "#fff",
    fontSize: "0.78rem",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backdropFilter: "blur(4px)",
  },
  previewRail: {
    display: "flex",
    gap: 8,
    overflowX: "auto",
    width: "100%",
    paddingBottom: 2,
  },
  previewThumbWrap: {
    position: "relative",
    width: 64,
    height: 64,
    flexShrink: 0,
    borderRadius: 12,
    overflow: "hidden",
    border: "2px solid transparent",
  },
  previewThumbWrapActive: { borderColor: "var(--brand-primary)" },
  previewThumbButton: {
    width: "100%",
    height: "100%",
    padding: 0,
    border: "none",
    background: "transparent",
    cursor: "pointer",
  },
  previewThumb: { width: "100%", height: "100%", objectFit: "cover" },
  previewRemoveButton: {
    position: "absolute",
    top: 4,
    right: 4,
    width: 18,
    height: 18,
    borderRadius: 6,
    border: "none",
    background: "rgba(17,24,39,0.6)",
    color: "#fff",
    fontSize: "0.65rem",
    cursor: "pointer",
    lineHeight: 1,
    padding: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  addMoreThumb: {
    width: 64,
    height: 64,
    flexShrink: 0,
    borderRadius: 12,
    border: "1.5px dashed #d1d5db",
    background: "var(--neutral-50)",
    color: "var(--neutral-500)",
    fontSize: "1.5rem",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  /* ── Loading ── */
  loadingSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    background: "var(--surface-panel)",
  },
  loadingDots: { display: "flex", gap: 8, alignItems: "center" },
  loadingDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "var(--brand-primary)",
    animation: "menuBounce 1.2s infinite ease-in-out",
  },
  loadingText: {
    margin: 0,
    color: "var(--neutral-600)",
    fontSize: "0.88rem",
    fontWeight: 500,
  },

  /* ── Select ── */
  selectSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    minHeight: 0,
    overflow: "hidden",
    touchAction: "pan-y" as CSSProperties["touchAction"],
  },
  stickyHero: {
    flexShrink: 0,
    background: "var(--surface-panel)",
    padding: "10px 16px 8px",
    borderBottom: "1px solid #e5e7eb",
  },
  menuHero: {
    width: "100%",
    height: 120,
    borderRadius: 14,
    overflow: "hidden",
    background: "var(--border-soft)",
  },
  menuHeroImage: { width: "100%", height: "100%", objectFit: "cover" },

  /* Party size */
  partySizeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "4px 0 6px",
  },
  partySizeLabel: {
    color: "var(--neutral-500)",
    fontSize: "0.7rem",
    fontWeight: 700,
    letterSpacing: "0.04em",
    marginRight: 6,
  },
  selectAllBtn: {
    border: "1.5px solid #e5e7eb",
    borderRadius: 10,
    padding: "6px 14px",
    background: "var(--surface-panel)",
    color: "var(--neutral-600)",
    fontSize: "0.78rem",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap" as CSSProperties["whiteSpace"],
  },
  selectAllBtnActive: {
    borderColor: "var(--brand-primary)",
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary)",
  },
  partySizeControls: {
    display: "flex",
    alignItems: "center",
    gap: 2,
    background: "var(--surface-muted)",
    borderRadius: 12,
    padding: "4px 10px",
  },
  partySizeBtn: {
    border: "none",
    background: "transparent",
    color: "var(--brand-primary)",
    fontSize: "1.15rem",
    fontWeight: 900,
    cursor: "pointer",
    padding: "0 5px",
    lineHeight: 1,
  },
  partySizeCount: {
    color: "var(--neutral-900)",
    fontSize: "1rem",
    fontWeight: 900,
    minWidth: 22,
    textAlign: "center" as CSSProperties["textAlign"],
  },

  pageTabRail: {
    display: "flex",
    gap: 6,
    overflowX: "auto",
    marginTop: 6,
    paddingBottom: 2,
  },
  pageTab: {
    flexShrink: 0,
    border: "1.5px solid #e5e7eb",
    borderRadius: 8,
    padding: "4px 14px",
    background: "var(--neutral-50)",
    color: "var(--neutral-600)",
    fontSize: "0.78rem",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  pageTabActive: {
    borderColor: "var(--brand-primary)",
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary)",
  },

  menuList: {
    flex: 1,
    overflowY: "scroll",
    minHeight: 0,
    padding: "8px 14px 12px",
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
    overscrollBehavior: "contain" as CSSProperties["overscrollBehavior"],
    background: "var(--surface-muted)",
  },
  restaurantText: {
    margin: "6px 2px 12px",
    color: "#a89880",
    fontSize: "0.72rem",
    fontWeight: 800,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as CSSProperties["textTransform"],
  },
  categoryGroup: { marginBottom: 20 },

  categoryHeader: {
    padding: "0 4px 8px",
    marginBottom: 0,
  },
  categoryBadge: {
    display: "inline-block",
    padding: "3px 12px",
    borderRadius: 999,
    fontSize: "0.72rem",
    fontWeight: 800,
    letterSpacing: "0.06em",
  },
  menuTitleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
    marginBottom: 2,
  },
  menuCard: {
    padding: "12px 14px 12px 16px",
    borderRadius: 16,
    background: "var(--surface-panel)",
    marginBottom: 8,
  },
  menuMetaRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    marginTop: 0,
    marginBottom: 3,
  },
  menuPriceInline: {
    fontSize: "0.72rem",
    fontWeight: 700,
  },
  menuCardSelected: {
    background: "var(--surface-panel)",
    boxShadow: "0 2px 14px rgba(0,0,0,0.10)",
  },
  menuCardDimmed: {
    background: "rgba(255,255,255,0.55)",
  },
  menuInfo: { flex: 1, minWidth: 0 },
  menuTitle: {
    margin: "0 0 3px",
    color: "var(--neutral-900)",
    fontSize: "0.95rem",
    fontWeight: 700,
    lineHeight: 1.35,
  },
  menuPrice: {
    fontWeight: 800,
    fontSize: "0.88rem",
    flexShrink: 0,
  },
  menuMeta: {
    margin: "3px 0 0",
    color: "#b0a898",
    fontSize: "0.72rem",
    fontWeight: 600,
    letterSpacing: "0.01em",
  },
  menuDescription: {
    margin: "4px 0 0",
    color: "var(--neutral-600)",
    fontSize: "0.72rem",
    lineHeight: 1.5,
  },

  /* Right column: HOT/ICE stack + toggle */
  cardRight: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 6,
    flexShrink: 0,
  },
  tempStack: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    alignItems: "center",
  },
  /* HOT / ICE buttons */
  tempBtn: {
    border: "1.5px solid #e5e7eb",
    borderRadius: 999,
    padding: "2px 10px",
    background: "var(--surface-panel)",
    color: "var(--neutral-500)",
    fontSize: "0.65rem",
    fontWeight: 700,
    cursor: "pointer",
    minWidth: 40,
    textAlign: "center" as CSSProperties["textAlign"],
  },
  tempBtnHot: {
    borderColor: "#ef4444",
    background: "#fef2f2",
    color: "#ef4444",
  },
  tempBtnIce: {
    borderColor: "#2196F3",
    background: "#e3f2fd",
    color: "#2196F3",
  },

  /* Quantity controls */
  quantityRow: {
    display: "inline-flex",
    alignItems: "center",
    gap: 0,
    marginTop: 8,
    border: "1px solid #58C9D4",
    borderRadius: 20,
    alignSelf: "flex-start",
    overflow: "hidden",
    background: "var(--surface-panel)",
  },
  quantityBtn: {
    width: 26,
    height: 22,
    borderRadius: 0,
    border: "none",
    background: "transparent",
    color: "var(--brand-primary)",
    fontSize: "1rem",
    fontWeight: 900,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1,
    padding: 0,
  },
  quantityCount: {
    color: "var(--brand-primary)",
    fontSize: "0.72rem",
    fontWeight: 800,
    minWidth: 44,
    textAlign: "center" as CSSProperties["textAlign"],
    padding: "0 2px",
    lineHeight: "22px",
  },

  /* Serving warning */
  servingWarning: {
    margin: "0 14px 8px",
    padding: "10px 14px",
    borderRadius: 12,
    background: "#fffbeb",
    border: "1.5px solid #fde68a",
    color: "#92400e",
    fontSize: "0.76rem",
    lineHeight: 1.5,
    flexShrink: 0,
  },
  toggle: {
    position: "relative",
    width: 44,
    height: 24,
    flexShrink: 0,
    border: "none",
    borderRadius: 999,
    cursor: "pointer",
    marginTop: 2,
  },
  toggleOn: { background: "var(--brand-primary)" },
  toggleOff: { background: "var(--border-soft)" },
  toggleThumb: {
    position: "absolute",
    top: 4,
    width: 16,
    height: 16,
    borderRadius: "50%",
    background: "var(--surface-panel)",
    transition: "left 0.16s ease",
    boxShadow: "0 1px 4px rgba(0,0,0,0.18)",
  },
  toggleThumbOn: { left: 24 },
  toggleThumbOff: { left: 4 },
  bottomBar: {
    flexShrink: 0,
    padding: "12px 16px 16px",
    background: "var(--surface-panel)",
    borderTop: "1px solid #e5e7eb",
  },
  orderButton: {
    width: "100%",
    border: "none",
    borderRadius: 16,
    padding: "15px 20px",
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 900,
    cursor: "pointer",
    fontSize: "1rem",
    letterSpacing: "-0.01em",
  },
  orderButtonDisabled: {
    background: "var(--border-soft)",
    color: "var(--neutral-500)",
    cursor: "not-allowed",
  },

  /* ── Order ── */
  orderSection: {
    flex: 1,
    padding: "8px 14px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
    overflowY: "auto",
    minHeight: 0,
    background: "var(--surface-muted)",
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
  },
  englishCard: {
    borderRadius: 14,
    background: "var(--surface-panel)",
    border: "1.5px solid #e5e7eb",
    padding: "14px 16px",
    position: "relative",
    flexShrink: 0,
  },
  englishMessage: {
    margin: 0,
    color: "var(--neutral-900)",
    fontSize: "0.93rem",
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    fontWeight: 400,
  },
  noteExpandedBox: {
    flexShrink: 0,
    borderRadius: 14,
    border: "1.5px solid #e5e7eb",
    background: "var(--surface-panel)",
    padding: "14px 16px",
  },
  noteBoxDivider: {
    width: "100%",
    height: 1,
    background: "#f3f4f6",
    margin: "10px 0",
  },
  noteToggleBtn: {
    width: "100%",
    flexShrink: 0,
    border: "1.5px dashed #d1d5db",
    borderRadius: 14,
    padding: "13px 16px",
    background: "var(--surface-panel)",
    fontSize: "0.88rem",
    cursor: "pointer",
    textAlign: "left" as CSSProperties["textAlign"],
    display: "flex",
    alignItems: "center",
  },
  noteTextarea: {
    width: "100%",
    borderRadius: 12,
    border: "1.5px solid #f3f4f6",
    padding: "10px 44px 10px 12px",
    fontSize: "0.88rem",
    fontFamily: "inherit",
    lineHeight: 1.55,
    color: "var(--neutral-900)",
    background: "var(--neutral-50)",
    resize: "none" as CSSProperties["resize"],
    outline: "none",
    boxSizing: "border-box" as CSSProperties["boxSizing"],
    display: "block",
  },
  textareaEnterBtn: {
    position: "absolute",
    bottom: 8,
    right: 8,
    width: 28,
    height: 28,
    borderRadius: 8,
    border: "none",
    background: "var(--brand-primary)",
    color: "#ffffff",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    flexShrink: 0,
  },
  infoRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    color: "var(--neutral-500)",
    fontSize: "0.76rem",
    padding: "0 2px",
    flexShrink: 0,
  },
  infoIcon: {
    width: 16,
    height: 16,
    borderRadius: "50%",
    background: "var(--border-soft)",
    display: "grid",
    placeItems: "center",
    fontSize: "0.6rem",
    fontWeight: 800,
    color: "var(--neutral-600)",
    flexShrink: 0,
  },
  infoText: { fontSize: "0.76rem" },

  /* Korean card */
  koreanCard: {
    flex: 1,
    minHeight: 0,
    borderRadius: 18,
    background: "var(--surface-panel)",
    border: "1px solid #58C9D4",
    padding: "16px 20px 14px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    gap: 10,
  },
  koreanMessage: {
    margin: 0,
    color: "var(--neutral-900)",
    fontSize: "1.18rem",
    fontWeight: 800,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
    flex: 1,
    minHeight: 0,
    overflowY: "auto" as CSSProperties["overflowY"],
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
  },
  koreanActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    alignSelf: "flex-end",
  },
  koreanIconButton: {
    width: 38,
    height: 38,
    borderRadius: 12,
    border: "1px solid #e5e7eb",
    background: "var(--neutral-50)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
  },

  /* USD card */
  usdCard: {
    flexShrink: 0,
    borderRadius: 14,
    background: "var(--surface-panel)",
    border: "1.5px solid #e5e7eb",
    padding: "10px 14px 8px",
  },
  usdRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 3,
  },
  usdLabel: {
    color: "var(--neutral-600)",
    fontSize: "0.74rem",
    fontWeight: 700,
    letterSpacing: "0.02em",
  },
  usdAmounts: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  krwText: {
    color: "var(--neutral-900)",
    fontSize: "0.9rem",
    fontWeight: 700,
  },
  usdText: {
    color: "var(--brand-primary)",
    fontSize: "0.9rem",
    fontWeight: 800,
  },
  usdCurrency: {
    fontSize: "0.7rem",
    fontWeight: 600,
  },
  usdLoading: {
    color: "var(--neutral-500)",
    fontSize: "0.78rem",
  },
  usdDisclaimer: {
    margin: 0,
    color: "var(--neutral-500)",
    fontSize: "0.68rem",
    lineHeight: 1.4,
  },

  doneButton: {
    flexShrink: 0,
    width: "100%",
    border: "none",
    borderRadius: 14,
    padding: "13px 18px",
    background: "var(--brand-primary)",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    fontSize: "0.93rem",
    letterSpacing: "-0.01em",
  },

  /* Korean fullscreen — intentional dark overlay */
  fullscreenOverlay: {
    position: "absolute",
    inset: 0,
    background: "#111827",
    zIndex: 10,
    display: "flex",
    flexDirection: "column",
  },
  fullscreenHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "20px 20px 0 26px",
    flexShrink: 0,
  },
  fullscreenLabel: {
    margin: 0,
    color: "rgba(255,255,255,0.35)",
    fontSize: "0.7rem",
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase" as CSSProperties["textTransform"],
  },
  fullscreenClose: {
    border: "none",
    background: "rgba(255,255,255,0.08)",
    color: "rgba(255,255,255,0.65)",
    width: 34,
    height: 34,
    borderRadius: 10,
    fontSize: "0.85rem",
    cursor: "pointer",
    flexShrink: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  fullscreenText: {
    flex: 1,
    margin: 0,
    padding: "28px 28px 20px",
    color: "#ffffff",
    fontSize: "2rem",
    fontWeight: 900,
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    overflowY: "auto" as CSSProperties["overflowY"],
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
  },
  fullscreenFooter: {
    flexShrink: 0,
    padding: "10px 22px 40px",
  },
  fullscreenSpeakBtn: {
    width: "100%",
    border: "1.5px solid rgba(255,255,255,0.12)",
    background: "rgba(255,255,255,0.06)",
    color: "#ffffff",
    borderRadius: 14,
    padding: "14px 24px",
    fontSize: "0.95rem",
    fontWeight: 700,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },

  /* USD pill in select screen */
  usdPill: {
    display: "inline-block",
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary)",
    borderRadius: 6,
    padding: "1px 7px",
    fontSize: "0.67rem",
    fontWeight: 700,
    marginLeft: 6,
    verticalAlign: "middle",
  },

  carouselPrevBtn: {
    position: "absolute",
    left: 8,
    top: "50%",
    transform: "translateY(-50%)",
    border: "none",
    background: "transparent",
    color: "var(--neutral-600)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 6,
    zIndex: 2,
  },
  carouselNextBtn: {
    position: "absolute",
    right: 8,
    top: "50%",
    transform: "translateY(-50%)",
    border: "none",
    background: "transparent",
    color: "var(--neutral-600)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 6,
    zIndex: 2,
  },

  /* ── Order swipe carousel ── */
  orderCarousel: {
    flexShrink: 0,
    display: "flex",
    overflowX: "scroll",
    scrollSnapType: "x mandatory" as CSSProperties["scrollSnapType"],
    scrollbarWidth: "none" as CSSProperties["scrollbarWidth"],
    width: "100%",
  },
  orderSlide: {
    flexShrink: 0,
    width: "100%",
    scrollSnapAlign: "start" as CSSProperties["scrollSnapAlign"],
    padding: "0 2px",
    boxSizing: "border-box" as CSSProperties["boxSizing"],
  },
  orderSlideCard: {
    borderRadius: 18,
    background: "var(--surface-panel)",
    border: "none",
    padding: "12px 30px 12px 30px",
    minHeight: 0,
    boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
  },
  orderSlideCounter: {
    display: "inline-block",
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary)",
    fontSize: "0.65rem",
    fontWeight: 800,
    letterSpacing: "0.08em",
    padding: "2px 8px",
    borderRadius: 20,
    marginBottom: 8,
    border: "1px solid #e6f9f9",
  },
  orderSlideName: {
    margin: "0 0 4px",
    color: "var(--neutral-900)",
    fontSize: "1.1rem",
    fontWeight: 900,
    lineHeight: 1.2,
    letterSpacing: "-0.02em",
  },
  orderSlideOriginal: {
    margin: 0,
    color: "#b0a898",
    fontSize: "0.75rem",
    fontWeight: 500,
  },
  orderSlideRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginTop: 10,
    flexWrap: "wrap" as CSSProperties["flexWrap"],
  },
  orderQtyBadge: {
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary)",
    borderRadius: 20,
    padding: "3px 10px",
    fontSize: "0.76rem",
    fontWeight: 900,
    border: "1px solid #e6f9f9",
  },
  orderPriceHint: {
    color: "var(--neutral-800)",
    fontSize: "0.85rem",
    fontWeight: 800,
  },
  orderUsdHint: {
    color: "var(--neutral-500)",
    fontSize: "0.78rem",
    fontWeight: 500,
  },
  slideTempRow: {
    display: "flex",
    gap: 6,
    marginTop: 12,
    flexWrap: "wrap" as CSSProperties["flexWrap"],
  },
  slideTempBtn: {
    border: "1.5px solid #e5e7eb",
    borderRadius: 999,
    padding: "4px 12px",
    background: "var(--neutral-50)",
    color: "var(--neutral-500)",
    fontSize: "0.72rem",
    fontWeight: 700,
    cursor: "pointer",
    letterSpacing: "0.04em",
  },
  slideTempBtnHot: {
    borderColor: "#ef4444",
    background: "#fef2f2",
    color: "#ef4444",
  },
  slideTempBtnCold: {
    borderColor: "#2196F3",
    background: "#e3f2fd",
    color: "#2196F3",
  },
  addNoteBtn: {
    flexShrink: 0,
    width: "100%",
    border: "1.5px dashed #c8bfb5",
    borderRadius: 14,
    padding: "10px 16px",
    background: "#fdfaf5",
    color: "#a89880",
    fontSize: "0.82rem",
    fontWeight: 600,
    cursor: "pointer",
    textAlign: "left" as CSSProperties["textAlign"],
  },

  /* Error */
  errorSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    gap: 12,
    padding: "24px",
    textAlign: "center",
    background: "var(--surface-panel)",
  },
  errorTitle: { margin: 0, color: "var(--neutral-900)", fontWeight: 800, fontSize: "1rem" },
  errorBody: { margin: 0, color: "var(--neutral-600)", lineHeight: 1.55 },
};
