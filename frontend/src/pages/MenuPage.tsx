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
}

type Step = "upload" | "preview" | "loading" | "select" | "order" | "error";

const CATEGORY_EMOJI: Record<MenuCategory, string> = {
  "메인메뉴": "🍽️",
  사이드: "🥗",
  "음료/주류": "🍺",
  디저트: "🍰",
  기타: "📋",
};

const CATEGORY_LABEL: Record<MenuCategory, string> = {
  "메인메뉴": "Main",
  사이드: "Side",
  "음료/주류": "Drinks",
  디저트: "Dessert",
  기타: "Other",
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

  const fileRef = useRef<HTMLInputElement>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const ocrRequestRef = useRef(false);
  const selectSectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    return () => {
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
      cancelSpeech();
    };
  }, [previewUrls]);

  // Fetch live KRW→USD rate when entering order screen
  useEffect(() => {
    if (step !== "order") return;
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

  const englishOrderMessage = useMemo(() => {
    if (!selectedItems.length) return "";
    const menuSentence = selectedItems
      .map((item) => {
        const qty = item.quantity > 1 ? `${item.quantity} servings of ` : "";
        const price = item.price > 0 ? ` (${(item.price * item.quantity).toLocaleString()} won)` : "";
        return `${qty}${item.translated}${price}`;
      })
      .join(", ");
    const base = `Excuse me, I would like to order ${menuSentence}, please.`;
    return orderNote.trim() ? `${base} ${orderNote.trim()}` : base;
  }, [orderNote, selectedItems]);

  const koreanOrderMessage = useMemo(() => {
    if (!selectedItems.length) return "";
    const menuSentence = selectedItems
      .map((item) => `${item.original} ${item.quantity}인분`)
      .join(", ");
    const base = `사장님 여기 ${menuSentence} 주세요.`;
    const noteInKorean = translatedNote.trim();
    return noteInKorean ? `${base}\n\n${noteInKorean}` : base;
  }, [orderNote, translatedNote, selectedItems]);

  const totalKRW = useMemo(
    () => selectedItems.reduce((sum, item) => sum + item.price * item.quantity, 0),
    [selectedItems]
  );

  const hasServingWarning = useMemo(
    () => selectedItems.some((item) => item.quantity < partySize),
    [selectedItems, partySize]
  );

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

  const handleGoToOrder = () => {
    if (!selectedItems.length) return;
    setEditingNote(false);
    setStep("order");
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
      `}</style>

      <input
        ref={fileRef}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp,image/bmp,image/tiff"
        multiple
        onChange={handleFileChange}
        style={styles.hiddenInput}
      />

      <div style={{
          ...styles.phone,
          ...(step === "loading" ? { background: "linear-gradient(180deg, #F2FFFF 65.72%, #FFFBF1 93.23%)" } : null),
        }}>
        <header style={styles.header}>
          <button
            type="button"
            onClick={step === "upload" ? undefined : handleBackButton}
            style={{ ...styles.backButton, ...(step === "upload" ? styles.backButtonHidden : null) }}
            aria-label="Go back"
          >
            ‹
          </button>
          <h1 style={styles.headerTitle}>Menu Translation</h1>
          <div style={styles.headerSpacer} />
        </header>

        {/* ── Upload ── */}
        {step === "upload" ? (
          <section style={styles.uploadSection}>
            <h2 style={styles.uploadTitle}>Snap a menu to order instantly</h2>
            <p style={styles.uploadSubtitle}>
              We will translate your choices so you can order simply by showing your screen.
            </p>
            <button type="button" onClick={handleOpenPicker} style={styles.uploadBox}>
              <span style={styles.plusButton}>+</span>
              <p style={styles.uploadCopy}>Upload Menu Photo</p>
            </button>
            <button type="button" disabled style={styles.translateButtonDisabled}>
              Translate
            </button>
          </section>
        ) : null}

        {/* ── Preview ── */}
        {step === "preview" ? (
          <section style={styles.previewSection}>
            <h2 style={styles.uploadTitle}>Snap a menu to order instantly</h2>
            <p style={styles.uploadSubtitle}>
              We will translate your choices so you can order simply by showing your screen.
            </p>

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
                ✕
              </button>
            </div>

            {previewUrls.length > 1 ? (
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
                      ✕
                    </button>
                  </div>
                ))}
                {previewUrls.length < 5 ? (
                  <button type="button" onClick={handleOpenPicker} style={styles.addMoreThumb}>+</button>
                ) : null}
              </div>
            ) : null}

            <button type="button" onClick={handleTranslate} style={styles.translateButton}>
              Translate {selectedFiles.length > 1 ? `${selectedFiles.length} Photos` : "Photo"}
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
            <p style={styles.loadingText}>Translating menu</p>
          </section>
        ) : null}

        {/* ── Select ── */}
        {step === "select" ? (
          <section ref={selectSectionRef} style={styles.selectSection}>
            {/* Fixed: photo + page tabs */}
            <div style={styles.stickyHero}>
              <div style={styles.menuHero}>
                {previewUrls[activePreviewIndex] ? (
                  <img
                    src={previewUrls[activePreviewIndex]}
                    alt=""
                    style={styles.menuHeroImage}
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                  />
                ) : null}
              </div>

              {/* Party size + select-all row */}
              <div style={styles.partySizeRow}>
                <span style={styles.partySizeLabel}>👥 Party size</span>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
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

              {groupedByCategory.map(([category, items]) => (
                <div key={category} style={styles.categoryGroup}>
                  <div style={styles.categoryHeader}>
                    <span style={styles.categoryEmoji}>{CATEGORY_EMOJI[category]}</span>
                    <span style={styles.categoryLabel}>{CATEGORY_LABEL[category]}</span>
                  </div>

                  {items.map((item) => (
                    <article
                      key={item.id}
                      style={{
                        ...styles.menuCard,
                        ...(item.visible ? styles.menuCardSelected : styles.menuCardDimmed),
                      }}
                    >
                      <div style={styles.menuInfo}>
                        <p style={{ ...styles.menuTitle, fontWeight: item.visible ? 800 : 500 }}>
                          {item.translated}{" "}
                          {item.price > 0 ? (
                            <span style={{
                              ...styles.menuPrice,
                              color: item.visible ? "#FF3B30" : "#9ca3af",
                            }}>
                              {item.price.toLocaleString()} won
                            </span>
                          ) : null}
                        </p>
                        <p style={styles.menuMeta}>{item.original}</p>
                        <p style={styles.menuDescription}>{item.description}</p>

                        {/* Quantity controls — only shown when item is selected */}
                        {item.visible ? (
                          <div style={styles.quantityRow}>
                            <button
                              type="button"
                              onClick={() => updateQuantity(item.id, -1)}
                              disabled={item.quantity <= 1}
                              style={{
                                ...styles.quantityBtn,
                                opacity: item.quantity <= 1 ? 0.35 : 1,
                              }}
                            >−</button>
                            <span style={styles.quantityCount}>{item.quantity} serving{item.quantity > 1 ? "s" : ""}</span>
                            <button
                              type="button"
                              onClick={() => updateQuantity(item.id, 1)}
                              style={styles.quantityBtn}
                            >+</button>
                          </div>
                        ) : null}
                      </div>

                      <button
                        type="button"
                        onClick={() => toggleItem(item.id)}
                        style={{
                          ...styles.toggle,
                          ...(item.visible ? styles.toggleOn : styles.toggleOff),
                        }}
                        aria-label={item.visible ? "Disable item" : "Enable item"}
                      >
                        <span style={{
                          ...styles.toggleThumb,
                          ...(item.visible ? styles.toggleThumbOn : styles.toggleThumbOff),
                        }} />
                      </button>
                    </article>
                  ))}
                </div>
              ))}
            </div>

            {hasServingWarning && selectedItems.length > 0 ? (
              <div style={styles.servingWarning}>
                ⚠️ Some items may require minimum {partySize} servings for your group. Korean restaurants often have minimum order quantities — please confirm with staff.
              </div>
            ) : null}

            <div style={styles.bottomBar}>
              <button
                type="button"
                onClick={handleGoToOrder}
                disabled={!selectedItems.length}
                style={{
                  ...styles.orderButton,
                  ...(!selectedItems.length ? styles.orderButtonDisabled : null),
                }}
              >
                {selectedItems.length > 0 ? `Order (${selectedItems.length})` : "Order"}
              </button>
            </div>
          </section>
        ) : null}

        {/* ── Order ── */}
        {step === "order" ? (
          <section style={styles.orderSection}>
            {/* 1. English card — user confirms */}
            <div style={styles.englishCard}>
              <p style={styles.englishMessage}>{englishOrderMessage}</p>

              {editingNote ? (
                <div style={styles.noteEditArea}>
                  <textarea
                    value={orderNote}
                    onChange={(e) => {
                      setOrderNote(e.target.value);
                      setTranslatedNote("");
                    }}
                    placeholder="Any additional requests? (e.g. no spicy, extra napkins)"
                    style={styles.noteTextarea}
                    rows={2}
                    autoFocus
                  />
                  <button
                    type="button"
                    disabled={translatingNote}
                    onClick={async () => {
                      const note = orderNote.trim();
                      if (!note) {
                        setTranslatedNote("");
                        setEditingNote(false);
                        return;
                      }
                      setTranslatingNote(true);
                      try {
                        const korean = await translateToKorean(note);
                        setTranslatedNote(korean);
                      } catch (err) {
                        console.error("[translation] failed:", err);
                        setTranslatedNote("");
                      } finally {
                        setTranslatingNote(false);
                        setEditingNote(false);
                      }
                    }}
                    style={styles.noteSaveBtn}
                  >
                    {translatingNote ? "Translating…" : "Save"}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setEditingNote(true)}
                  style={styles.editButton}
                  aria-label="Add request"
                >
                  ✏️
                </button>
              )}
            </div>

            {/* 2. Info row */}
            <div style={styles.infoRow}>
              <span style={styles.infoIcon}>i</span>
              <span style={styles.infoText}>Please show this screen to the staff.</span>
            </div>

            {/* 3. Korean card — for restaurant staff */}
            <div style={styles.koreanCard}>
              <p style={styles.koreanMessage}>{koreanOrderMessage}</p>
              <div style={styles.koreanActions}>
                <button
                  type="button"
                  onClick={() => setKoreanFullscreen(true)}
                  style={styles.koreanIconButton}
                  aria-label="Fullscreen"
                >
                  <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                    <path d="M1 6V2a1 1 0 0 1 1-1h4M11 1h4a1 1 0 0 1 1 1v4M17 12v4a1 1 0 0 1-1 1h-4M7 17H3a1 1 0 0 1-1-1v-4"
                      stroke="#18c3c8" strokeWidth="1.6" strokeLinecap="round"/>
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={handleSpeak}
                  style={styles.koreanIconButton}
                  aria-label={speaking ? "Stop" : "Play TTS"}
                >
                  {speaking ? (
                    <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                      <rect x="3" y="3" width="4" height="12" rx="1" fill="#18c3c8"/>
                      <rect x="11" y="3" width="4" height="12" rx="1" fill="#18c3c8"/>
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
                      <path d="M3 6.5h2.5L9 3.5v11L5.5 11.5H3a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1z" fill="#18c3c8"/>
                      <path d="M12 6a4 4 0 0 1 0 6M14 3.5a7.5 7.5 0 0 1 0 11" stroke="#18c3c8" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                  )}
                </button>
              </div>
            </div>
            {ttsError ? <p style={styles.errorBody}>{ttsError}</p> : null}

            {/* 4. USD conversion card */}
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
                    1 USD ≈ ₩{Math.round(1 / exchangeRate).toLocaleString()} · Live rate · For reference only, actual price may vary
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
            <button
              type="button"
              onClick={() => setKoreanFullscreen(false)}
              style={styles.fullscreenClose}
              aria-label="Close"
            >
              ✕
            </button>
            <p style={styles.fullscreenText}>{koreanOrderMessage}</p>
            <button type="button" onClick={handleSpeak} style={styles.fullscreenSpeakBtn}>
              {speaking ? "■  Stop" : "▶  Read aloud"}
            </button>
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
    minHeight: "100dvh",
    background: "#f5f5f5",
    padding: "24px 16px 40px",
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "center",
    fontFamily: "'Pretendard Variable', 'Nunito', 'Apple SD Gothic Neo', sans-serif",
    overflowX: "hidden",
  },
  hiddenInput: { display: "none" },
  phone: {
    width: "100%",
    maxWidth: 390,
    // Fixed height so the inner flex scroll works correctly
    height: "calc(100dvh - 64px)",
    maxHeight: 900,
    background: "#ffffff",
    borderRadius: 34,
    boxShadow: "0 24px 80px rgba(15, 23, 42, 0.12)",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    position: "relative",
  },
  header: {
    display: "grid",
    gridTemplateColumns: "40px 1fr 40px",
    alignItems: "center",
    minHeight: 54,
    padding: "20px 22px 20px 16px",
    flexShrink: 0,
  },
  backButton: {
    border: "none",
    background: "transparent",
    fontSize: "2rem",
    lineHeight: 1,
    color: "#9ca3af",
    cursor: "pointer",
    padding: 0,
  },
  backButtonHidden: { visibility: "hidden", cursor: "default" },
  headerTitle: {
    margin: 0,
    textAlign: "center",
    fontSize: "1rem",
    fontWeight: 800,
    color: "#111827",
  },
  headerSpacer: { width: 40 },

  /* ── Upload ── */
  uploadSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "28px 16px 34px",
    overflowY: "auto",
  },
  uploadTitle: {
    margin: "0 0 10px",
    fontSize: "1.25rem",
    fontWeight: 800,
    color: "#111827",
    textAlign: "center",
    lineHeight: 1.3,
  },
  uploadSubtitle: {
    margin: "0 0 24px",
    fontSize: "0.875rem",
    color: "#6b7280",
    textAlign: "center",
    lineHeight: 1.55,
    maxWidth: 300,
  },
  uploadBox: {
    flex: 1,
    width: "100%",
    maxWidth: 362,
    minHeight: 200,
    borderRadius: 25,
    border: "1.5px dashed #d1d5db",
    background: "#f9fafb",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    cursor: "pointer",
    marginBottom: 24,
  },
  plusButton: {
    width: 64,
    height: 64,
    borderRadius: "50%",
    background: "#01c0c0",
    color: "#ffffff",
    fontSize: "2.9rem",
    lineHeight: "64px",
    textAlign: "center",
    display: "block",
    flexShrink: 0,
  },
  uploadCopy: { margin: 0, color: "#4d4d4d", fontSize: 17, fontWeight: 700 },
  translateButtonDisabled: {
    width: "100%",
    maxWidth: 362,
    border: "none",
    borderRadius: 50,
    height: 56,
    background: "#f6f6f6",
    color: "#d1d5db",
    fontSize: 17,
    fontWeight: 600,
    cursor: "not-allowed",
  },

  /* ── Preview ── */
  previewSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "12px 15px 34px",
    gap: 14,
    overflowY: "auto",
  },
  previewMainFrame: {
    width: "100%",
    maxWidth: 363,
    height: 340,
    borderRadius: 25,
    background: "#d9d9d9",
    overflow: "hidden",
    flexShrink: 0,
  },
  previewLargeImage: { width: "100%", height: "100%", objectFit: "cover" },
  previewXOverlay: {
    position: "absolute",
    top: 12,
    right: 12,
    width: 30,
    height: 30,
    borderRadius: "50%",
    border: "none",
    background: "rgba(0,0,0,0.52)",
    color: "#fff",
    fontSize: "0.85rem",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  previewRail: {
    display: "flex",
    gap: 10,
    overflowX: "auto",
    width: "100%",
    maxWidth: 363,
    paddingBottom: 4,
  },
  previewThumbWrap: {
    position: "relative",
    width: 72,
    height: 72,
    flexShrink: 0,
    borderRadius: 18,
    overflow: "hidden",
    border: "2px solid transparent",
  },
  previewThumbWrapActive: { borderColor: "#18c3c8" },
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
    borderRadius: "50%",
    border: "none",
    background: "rgba(0,0,0,0.58)",
    color: "#fff",
    fontSize: "0.68rem",
    cursor: "pointer",
    lineHeight: 1,
    padding: 0,
  },
  addMoreThumb: {
    width: 72,
    height: 72,
    flexShrink: 0,
    borderRadius: 18,
    border: "2px dashed #d1d5db",
    background: "#f9fafb",
    color: "#6b7280",
    fontSize: "1.8rem",
    cursor: "pointer",
  },
  translateButton: {
    width: "100%",
    maxWidth: 362,
    marginTop: "auto",
    border: "none",
    borderRadius: 50,
    height: 56,
    background: "#01c0c0",
    color: "#ffffff",
    fontSize: 17,
    fontWeight: 700,
    cursor: "pointer",
  },

  /* ── Loading ── */
  loadingSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 14,
    paddingBottom: 60,
    background: "linear-gradient(180deg, #F2FFFF 65.72%, #FFFBF1 93.23%)",
  },
  loadingDots: { display: "flex", gap: 10, alignItems: "center" },
  loadingDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#18c3c8",
    animation: "menuBounce 1.2s infinite ease-in-out",
  },
  loadingText: { margin: 0, color: "#111827", fontSize: 17, fontWeight: 400 },

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
    background: "#ffffff",
    padding: "12px 14px 10px",
    boxShadow: "0 4px 16px rgba(15,23,42,0.06)",
  },
  menuHero: {
    width: "100%",
    height: 160,
    borderRadius: 24,
    overflow: "hidden",
    background: "#e5e7eb",
  },
  menuHeroImage: { width: "100%", height: "100%", objectFit: "cover" },

  /* Party size */
  partySizeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 2px 2px",
  },
  partySizeLabel: {
    color: "#374151",
    fontSize: "0.85rem",
    fontWeight: 700,
  },
  selectAllBtn: {
    border: "1.5px solid #e5e7eb",
    borderRadius: 999,
    padding: "4px 12px",
    background: "#f9fafb",
    color: "#6b7280",
    fontSize: "0.75rem",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap" as CSSProperties["whiteSpace"],
  },
  selectAllBtnActive: {
    borderColor: "#18c3c8",
    background: "#E4F8F8",
    color: "#18c3c8",
  },
  partySizeControls: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    background: "#f3f4f6",
    borderRadius: 999,
    padding: "4px 10px",
  },
  partySizeBtn: {
    border: "none",
    background: "transparent",
    color: "#18c3c8",
    fontSize: "1.1rem",
    fontWeight: 800,
    cursor: "pointer",
    padding: "0 2px",
    lineHeight: 1,
  },
  partySizeCount: {
    color: "#111827",
    fontSize: "0.9rem",
    fontWeight: 800,
    minWidth: 16,
    textAlign: "center" as CSSProperties["textAlign"],
  },

  pageTabRail: {
    display: "flex",
    gap: 8,
    overflowX: "auto",
    marginTop: 6,
    paddingBottom: 2,
  },
  pageTab: {
    flexShrink: 0,
    border: "1.5px solid #e5e7eb",
    borderRadius: 999,
    padding: "6px 18px",
    background: "#f9fafb",
    color: "#6b7280",
    fontSize: "0.82rem",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  pageTabActive: {
    borderColor: "#18c3c8",
    background: "#E4F8F8",
    color: "#18c3c8",
  },

  // This div must scroll, NOT the outer page
  menuList: {
    flex: 1,
    overflowY: "scroll",      // force scroll track to appear
    minHeight: 0,
    padding: "10px 14px 10px",
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
    overscrollBehavior: "contain" as CSSProperties["overscrollBehavior"],
  },
  restaurantText: {
    margin: "4px 0 12px",
    color: "#9ca3af",
    fontSize: "0.75rem",
    fontWeight: 700,
  },
  categoryGroup: { marginBottom: 18 },
  categoryHeader: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 2px",
    marginBottom: 8,
    borderBottom: "1.5px solid #f0f0f0",
  },
  categoryEmoji: { fontSize: "0.95rem" },
  categoryLabel: {
    color: "#374151",
    fontSize: "0.88rem",
    fontWeight: 800,
    letterSpacing: "0.01em",
  },
  menuCard: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "13px 14px",
    borderRadius: 20,
    background: "#ffffff",
    boxShadow: "0 4px 14px rgba(15, 23, 42, 0.05)",
    marginBottom: 10,
    border: "1px solid #f3f4f6",
  },
  menuCardSelected: {
    background: "radial-gradient(115.28% 168.96% at 21.69% 6.52%, rgba(255, 251, 239, 0.80) 0%, rgba(255, 255, 255, 0.00) 100%), #C7F5F5",
    border: "1.5px solid #A8E5E3",
    boxShadow: "0 4px 14px rgba(24, 195, 200, 0.12)",
  },
  menuCardDimmed: { opacity: 0.5 },
  menuInfo: { flex: 1, minWidth: 0 },
  menuTitle: { margin: 0, color: "#111827", fontSize: "0.94rem", fontWeight: 800 },
  menuPrice: { color: "#FF3B30", fontWeight: 700 },
  menuMeta: { margin: "3px 0 0", color: "#9ca3af", fontSize: "0.72rem", fontWeight: 600 },
  menuDescription: { margin: "5px 0 0", color: "#6b7280", fontSize: "0.79rem", lineHeight: 1.45 },

  /* Quantity controls */
  quantityRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginTop: 8,
  },
  quantityBtn: {
    width: 26,
    height: 26,
    borderRadius: "50%",
    border: "1.5px solid #18c3c8",
    background: "#ffffff",
    color: "#18c3c8",
    fontSize: "1rem",
    fontWeight: 800,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    lineHeight: 1,
    padding: 0,
  },
  quantityCount: {
    color: "#111827",
    fontSize: "0.8rem",
    fontWeight: 700,
    minWidth: 60,
  },

  /* Serving warning */
  servingWarning: {
    margin: "0 14px",
    padding: "10px 14px",
    borderRadius: 14,
    background: "#FFF8E7",
    border: "1px solid #FFE082",
    color: "#92680A",
    fontSize: "0.78rem",
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
  },
  toggleOn: { background: "#18c3c8" },
  toggleOff: { background: "#e5e7eb" },
  toggleThumb: {
    position: "absolute",
    top: 3,
    width: 18,
    height: 18,
    borderRadius: "50%",
    background: "#ffffff",
    boxShadow: "0 2px 8px rgba(15, 23, 42, 0.16)",
    transition: "left 0.2s ease",
  },
  toggleThumbOn: { left: 23 },
  toggleThumbOff: { left: 3 },
  bottomBar: {
    flexShrink: 0,
    padding: "10px 14px 18px",
    background: "#ffffff",
    boxShadow: "0 -4px 16px rgba(15,23,42,0.05)",
  },
  orderButton: {
    width: "100%",
    border: "none",
    borderRadius: 999,
    padding: "14px 18px",
    background: "#18c3c8",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    fontSize: "1rem",
  },
  orderButtonDisabled: { background: "#d1d5db", cursor: "not-allowed" },

  /* ── Order ── */
  orderSection: {
    flex: 1,
    padding: "16px 14px 22px",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    overflowY: "auto",
    minHeight: 0,
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
  },
  englishCard: {
    borderRadius: 22,
    background: "#f5f5f5",
    border: "1px solid #ebebeb",
    padding: "18px 16px 14px",
    position: "relative",
    flexShrink: 0,
  },
  englishMessage: {
    margin: 0,
    color: "#111827",
    fontSize: "0.97rem",
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    fontWeight: 400,
    paddingRight: 28,
  },
  editButton: {
    position: "absolute",
    bottom: 12,
    right: 14,
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontSize: "1rem",
    padding: 0,
    lineHeight: 1,
    opacity: 0.55,
  },
  noteEditArea: {
    marginTop: 12,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  noteTextarea: {
    width: "100%",
    borderRadius: 12,
    border: "1.5px solid #d1d5db",
    padding: "10px 12px",
    fontSize: "0.9rem",
    fontFamily: "inherit",
    lineHeight: 1.5,
    color: "#111827",
    background: "#ffffff",
    resize: "none" as CSSProperties["resize"],
    outline: "none",
    boxSizing: "border-box" as CSSProperties["boxSizing"],
  },
  noteSaveBtn: {
    alignSelf: "flex-end",
    border: "none",
    borderRadius: 999,
    padding: "8px 20px",
    background: "#18c3c8",
    color: "#ffffff",
    fontWeight: 700,
    fontSize: "0.85rem",
    cursor: "pointer",
  },
  infoRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    color: "#9ca3af",
    fontSize: "0.82rem",
    padding: "0 2px",
    flexShrink: 0,
  },
  infoIcon: {
    width: 18,
    height: 18,
    borderRadius: "50%",
    background: "#f3f4f6",
    display: "grid",
    placeItems: "center",
    fontSize: "0.74rem",
    fontWeight: 800,
    color: "#6b7280",
    flexShrink: 0,
  },
  infoText: { fontSize: "0.82rem" },
  koreanCard: {
    flex: 1,
    minHeight: 160,
    borderRadius: 26,
    background: "radial-gradient(166.25% 90.27% at 13.26% 44.63%, rgba(255, 251, 239, 0.80) 0%, rgba(255, 255, 255, 0.48) 100%), #C7F5F5",
    padding: "22px 20px 18px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    gap: 16,
  },
  koreanMessage: {
    margin: 0,
    color: "#111827",
    fontSize: "1.08rem",
    fontWeight: 800,
    lineHeight: 1.55,
    whiteSpace: "pre-wrap",
    flex: 1,
    minHeight: 0,
    overflowY: "auto" as CSSProperties["overflowY"],
    WebkitOverflowScrolling: "touch" as CSSProperties["WebkitOverflowScrolling"],
  },
  koreanActions: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    alignSelf: "flex-end",
  },
  koreanIconButton: {
    width: 34,
    height: 34,
    borderRadius: "50%",
    border: "1.5px solid rgba(0,0,0,0.15)",
    background: "rgba(255,255,255,0.4)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
  },

  /* USD card */
  usdCard: {
    flexShrink: 0,
    borderRadius: 18,
    background: "#f9fafb",
    border: "1px solid #e5e7eb",
    padding: "14px 16px 12px",
  },
  usdRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  usdLabel: {
    color: "#6b7280",
    fontSize: "0.8rem",
    fontWeight: 700,
  },
  usdAmounts: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  krwText: {
    color: "#111827",
    fontSize: "0.95rem",
    fontWeight: 700,
  },
  usdText: {
    color: "#18c3c8",
    fontSize: "0.95rem",
    fontWeight: 800,
  },
  usdCurrency: {
    fontSize: "0.75rem",
    fontWeight: 600,
  },
  usdLoading: {
    color: "#9ca3af",
    fontSize: "0.8rem",
  },
  usdDisclaimer: {
    margin: 0,
    color: "#9ca3af",
    fontSize: "0.72rem",
    lineHeight: 1.4,
  },

  doneButton: {
    flexShrink: 0,
    width: "100%",
    border: "none",
    borderRadius: 999,
    padding: "14px 18px",
    background: "#18c3c8",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
    fontSize: "1rem",
  },

  /* Korean fullscreen */
  fullscreenOverlay: {
    position: "absolute",
    inset: 0,
    background: "#18c3c8",
    zIndex: 10,
    display: "flex",
    flexDirection: "column",
    padding: "28px 24px 32px",
  },
  fullscreenClose: {
    alignSelf: "flex-end",
    border: "none",
    background: "rgba(255,255,255,0.2)",
    color: "#ffffff",
    width: 36,
    height: 36,
    borderRadius: "50%",
    fontSize: "1rem",
    cursor: "pointer",
    marginBottom: 24,
    flexShrink: 0,
  },
  fullscreenText: {
    flex: 1,
    margin: 0,
    color: "#ffffff",
    fontSize: "1.6rem",
    fontWeight: 900,
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
  },
  fullscreenSpeakBtn: {
    flexShrink: 0,
    border: "2px solid rgba(255,255,255,0.5)",
    background: "transparent",
    color: "#ffffff",
    borderRadius: 999,
    padding: "12px 24px",
    fontSize: "1rem",
    fontWeight: 700,
    cursor: "pointer",
    marginTop: 24,
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
  },
  errorTitle: { margin: 0, color: "#111827", fontWeight: 800, fontSize: "1rem" },
  errorBody: { margin: 0, color: "#6b7280", lineHeight: 1.5 },
};
