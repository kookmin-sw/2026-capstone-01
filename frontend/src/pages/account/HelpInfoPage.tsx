import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

type HelpItem = {
  question: string;
  answer: string[];
};

type HelpCategory = {
  id: string;
  label: string;
  description: string;
  items: HelpItem[];
};

const helpCategories: HelpCategory[] = [
  {
    id: "basics",
    label: "Travel Basics",
    description: "Start here for internet, payments, convenience stores, and tax refund basics.",
    items: [
      { question: "Should I use SIM, eSIM, or portable Wi-Fi?", answer: ["eSIM is easiest if your phone supports it.", "Portable Wi-Fi is useful for groups.", "Buy at the airport or online before arrival."] },
      { question: "Can I pay by card in Korea?", answer: ["Cards are accepted almost everywhere.", "Keep some cash for markets, small buses, or older shops.", "Some foreign cards may fail at kiosks, so carry a backup."] },
      { question: "How do convenience stores work?", answer: ["CU, GS25, 7-Eleven, and emart24 are open late or 24 hours.", "You can buy snacks, SIM cards, T-money top-ups, and basic medicine.", "Ask staff to heat ready meals if needed."] },
      { question: "How should I use translation apps?", answer: ["Use camera translation for menus and signs.", "Keep sentences short and simple.", "Papago is often strong for Korean-English translation."] },
      { question: "What about receipts and tax refunds?", answer: ["Keep receipts for tax-free shopping.", "Look for Tax Free signs at stores.", "At the airport, follow the tax refund kiosk or counter instructions."] },
    ],
  },
  {
    id: "transport",
    label: "Transportation",
    description: "Move around Korea with T-money, subway, buses, airport trains, and taxis.",
    items: [
      { question: "Where can I buy and charge a T-money card?", answer: ["Buy one at convenience stores or subway stations.", "Charge with cash at stations or convenience stores.", "Tap when entering and leaving subway stations."] },
      { question: "How do I ride the subway?", answer: ["Check the line color and final destination direction.", "Transfer signs are clear inside stations.", "Use apps like Naver Map, KakaoMap, or Google Maps."] },
      { question: "How do I ride buses?", answer: ["Tap your T-money card when boarding.", "Tap again when getting off to receive transfer benefits.", "Press the stop bell before your stop."] },
      { question: "How do transfers work?", answer: ["Transfers are discounted when using the same transport card.", "Always tap out on buses and subways.", "Transfer time limits can vary by city."] },
      { question: "How do I check the last train or bus?", answer: ["Use Naver Map or KakaoMap and check the final departure time.", "Last trains can be earlier than expected.", "Plan extra time after 11 PM."] },
      { question: "How do I use the airport railroad?", answer: ["AREX connects Incheon Airport and Seoul Station.", "All-stop trains are cheaper.", "Express trains are faster and have reserved seats."] },
      { question: "How do I take a taxi?", answer: ["Use Kakao T if possible.", "Show your destination in Korean.", "Late-night fares can be higher."] },
    ],
  },
  {
    id: "food",
    label: "Food & Ordering",
    description: "Order food confidently, handle kiosks, and explain dietary needs.",
    items: [
      { question: "How do I order at a restaurant?", answer: ["Wait to be seated or choose a table if staff gestures.", "Many places have table bells or tablets.", "Pay at the counter after eating unless told otherwise."] },
      { question: "How do I use kiosks?", answer: ["Choose language if available.", "Select menu, pay by card, then keep the receipt number.", "If foreign card fails, ask staff for help."] },
      { question: "How do I ask for less spicy food?", answer: ["Say: 안 맵게 해주세요.", "Romanization: An maepge hae-juseyo.", "It means: Please make it not spicy."] },
      { question: "Are water and side dishes free?", answer: ["Water is often self-service.", "Many side dishes can be refilled for free.", "Ask politely if you need more."] },
      { question: "How do I explain allergies?", answer: ["Show the Korean name of your allergy.", "Say: 알레르기가 있어요.", "Romanization: Allereugiga isseoyo."] },
      { question: "Can I ask for halal or vegan food?", answer: ["Use clear phrases and translation apps.", "Halal and vegan options exist but are not everywhere.", "Search before visiting smaller restaurants."] },
      { question: "Can foreigners use delivery apps?", answer: ["Some apps require Korean phone verification.", "Hotel staff may help order.", "Restaurants with in-person pickup can be easier."] },
    ],
  },
  {
    id: "safety",
    label: "Safety & Emergency",
    description: "Know emergency numbers and what to do when something goes wrong.",
    items: [
      { question: "What emergency numbers should I know?", answer: ["112 is police.", "119 is fire and ambulance.", "1330 is Korea Travel Hotline with foreign language support."] },
      { question: "What if I lose my passport?", answer: ["Contact your embassy or consulate immediately.", "File a police report if needed.", "Keep digital copies of your passport and visa."] },
      { question: "What if I lose my wallet or item?", answer: ["Ask nearby staff first.", "Check police lost-and-found services.", "For subway items, contact the station office."] },
      { question: "How do I use hospitals or pharmacies?", answer: ["Pharmacies are marked 약.", "Bring your passport and insurance information.", "Use 1330 for medical guidance in English."] },
      { question: "Is it safe to move at night?", answer: ["Korea is generally safe, but stay aware.", "Use main streets and official taxis late at night.", "Share your route with a friend if traveling alone."] },
      { question: "How do I contact my embassy?", answer: ["Search your embassy's official emergency number before travel.", "Save it offline.", "Hotels can often help make calls."] },
    ],
  },
  {
    id: "culture",
    label: "Culture Tips",
    description: "Small local habits that make travel smoother and more respectful.",
    items: [
      { question: "Should I be quiet on the subway?", answer: ["Yes. Keep calls short and quiet.", "Use headphones.", "Priority seats should be left for people who need them."] },
      { question: "How does lining up work?", answer: ["Queue clearly and wait your turn.", "Subway platforms often have marked lines.", "Do not push into elevators or trains."] },
      { question: "What is the table bell for?", answer: ["Many restaurants use a call bell on the table.", "Press it when ready to order or ask for help.", "It is normal and not rude."] },
      { question: "Do I need to tip?", answer: ["No. Tipping is not expected in Korea.", "Service charges are usually included.", "A polite thank you is enough."] },
      { question: "When do I remove shoes?", answer: ["Remove shoes in some homes, guesthouses, and traditional restaurants.", "Look for shoe racks or raised floors.", "Follow what locals do."] },
      { question: "Why is it hard to find trash bins?", answer: ["Public bins can be limited.", "Carry small trash until you find one.", "Separate recycling when bins are labeled."] },
    ],
  },
  {
    id: "phrases",
    label: "Useful Korean Phrases",
    description: "Simple phrases for shopping, transport, food, and emergencies.",
    items: [
      { question: "How much is this?", answer: ["English: How much is this?", "Korean: 이거 얼마예요?", "Romanization: Igeo eolmayeyo?", "When to use: At markets, shops, or street food stalls."] },
      { question: "Where is the subway station?", answer: ["English: Where is the subway station?", "Korean: 지하철역이 어디예요?", "Romanization: Jihacheol-yeogi eodiyeyo?", "When to use: When asking for directions."] },
      { question: "I have an allergy.", answer: ["English: I have an allergy.", "Korean: 알레르기가 있어요.", "Romanization: Allereugiga isseoyo.", "When to use: Before ordering food."] },
      { question: "Please make it not spicy.", answer: ["English: Please make it not spicy.", "Korean: 안 맵게 해주세요.", "Romanization: An maepge hae-juseyo.", "When to use: When ordering Korean food."] },
      { question: "Can I pay by card?", answer: ["English: Can I pay by card?", "Korean: 카드로 결제할 수 있어요?", "Romanization: Kadeuro gyeoljehal su isseoyo?", "When to use: At shops, taxis, and restaurants."] },
      { question: "I lost my wallet.", answer: ["English: I lost my wallet.", "Korean: 지갑을 잃어버렸어요.", "Romanization: Jigabeul ireobeoryeosseoyo.", "When to use: At police stations, stations, or hotel desks."] },
      { question: "Please help me.", answer: ["English: Please help me.", "Korean: 도와주세요.", "Romanization: Dowajuseyo.", "When to use: In urgent or confusing situations."] },
    ],
  },
  {
    id: "app",
    label: "App Guide",
    description: "Use KRIP features to discover places, connect with people, and manage your trip.",
    items: [
      { question: "How do I find recommended places?", answer: ["Open Home and browse nearby places.", "Use search for names, categories, or keywords.", "Tap a place to see details and save favorites."] },
      { question: "How do I translate menus?", answer: ["Open the Menu tab.", "Upload or take a menu photo.", "Review translated items and save useful results."] },
      { question: "How do I write a Trip Mate post?", answer: ["Go to Mate.", "Tap the post icon.", "Add region, dates, companion type, and details."] },
      { question: "How do I add friends?", answer: ["Go to Mate or Chat.", "Search for a user or open a profile.", "Tap Add Friend and wait for acceptance."] },
      { question: "How do I use chat?", answer: ["Open the Chat tab inside Mate.", "Tap a room to send messages.", "Swipe a room to mute or leave if available."] },
      { question: "How do I manage notifications?", answer: ["Open My Page settings.", "Use Notification controls for global or room mute options.", "System push permission must also be allowed on your phone."] },
      { question: "How do I edit my profile?", answer: ["Open My Page.", "Use profile edit controls.", "Update photo, nickname, and travel preferences."] },
    ],
  },
];

export default function HelpInfoPage() {
  const navigate = useNavigate();
  const [activeCategoryId, setActiveCategoryId] = useState(helpCategories[0].id);
  const [openItemIndex, setOpenItemIndex] = useState<number | null>(null);
  const activeCategory = useMemo(
    () => helpCategories.find((category) => category.id === activeCategoryId) ?? helpCategories[0],
    [activeCategoryId]
  );

  function selectCategory(id: string): void {
    setActiveCategoryId(id);
    setOpenItemIndex(null);
  }

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <button type="button" style={styles.backButton} onClick={() => navigate(-1)} aria-label="Go back">
          <span aria-hidden="true">‹</span>
        </button>
        <div style={styles.titleBlock}>
          <h1 style={styles.title}>Foreigner Survival Guide</h1>
          <p style={styles.subtitle}>Essential tips for traveling in Korea</p>
        </div>
      </header>

      <nav style={styles.tabScroller} aria-label="Help categories">
        {helpCategories.map((category) => (
          <button
            key={category.id}
            type="button"
            style={{ ...styles.tab, ...(category.id === activeCategory.id ? styles.tabActive : {}) }}
            onClick={() => selectCategory(category.id)}
          >
            {category.label}
          </button>
        ))}
      </nav>

      <section style={styles.descriptionCard}>
        <strong style={styles.categoryTitle}>{activeCategory.label}</strong>
        <p style={styles.description}>{activeCategory.description}</p>
      </section>

      <section style={styles.accordionList}>
        {activeCategory.items.map((item, index) => {
          const isOpen = openItemIndex === index;
          return (
            <article key={item.question} style={styles.qaCard}>
              <button
                type="button"
                style={styles.questionButton}
                aria-expanded={isOpen}
                onClick={() => setOpenItemIndex(isOpen ? null : index)}
              >
                <span style={styles.qaMark}>Q</span>
                <span style={styles.questionText}>{item.question}</span>
                <span style={{ ...styles.chevron, ...(isOpen ? styles.chevronOpen : {}) }}>⌄</span>
              </button>
              <div style={{ ...styles.answerWrap, maxHeight: isOpen ? 360 : 0 }}>
                <div style={styles.answerInner}>
                  <span style={styles.answerMark}>A</span>
                  <ul style={styles.answerList}>
                    {item.answer.map((line) => (
                      <li key={line} style={styles.answerItem}>
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          );
        })}
      </section>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(18px + var(--app-safe-top)) 16px calc(92px + var(--app-safe-bottom))",
    background: "#f5f5f5",
    color: "var(--text-primary)",
    fontFamily: "'Pretendard Variable', 'Apple SD Gothic Neo', sans-serif",
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    gap: 12,
    maxWidth: 760,
    margin: "0 auto 18px",
  },
  backButton: {
    width: 38,
    height: 38,
    border: "none",
    borderRadius: "50%",
    background: "#ffffff",
    color: "var(--text-primary)",
    fontSize: "2rem",
    lineHeight: 0.8,
    display: "grid",
    placeItems: "center",
    boxShadow: "0 8px 20px rgba(33,33,33,0.08)",
    cursor: "pointer",
    flexShrink: 0,
  },
  titleBlock: { minWidth: 0 },
  title: {
    margin: 0,
    fontSize: "clamp(1.6rem, 7vw, 2.25rem)",
    lineHeight: 1.05,
    fontWeight: 900,
  },
  subtitle: {
    margin: "8px 0 0",
    color: "var(--neutral-700)",
    fontSize: "0.94rem",
    lineHeight: 1.45,
    fontWeight: 700,
  },
  tabScroller: {
    maxWidth: 760,
    margin: "0 auto",
    display: "flex",
    gap: 8,
    overflowX: "auto",
    padding: "2px 0 12px",
    scrollbarWidth: "none",
  },
  tab: {
    border: "1px solid #e2e2e2",
    borderRadius: 999,
    background: "#ffffff",
    color: "var(--neutral-700)",
    padding: "9px 14px",
    fontSize: "0.82rem",
    fontWeight: 850,
    whiteSpace: "nowrap",
    cursor: "pointer",
  },
  tabActive: {
    borderColor: "var(--brand-primary)",
    background: "var(--brand-primary)",
    color: "#ffffff",
  },
  descriptionCard: {
    maxWidth: 760,
    margin: "0 auto 14px",
    padding: 18,
    borderRadius: 22,
    background: "#ffffff",
    boxShadow: "0 12px 28px rgba(33,33,33,0.07)",
  },
  categoryTitle: {
    color: "var(--brand-primary-deep)",
    fontSize: "0.86rem",
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  },
  description: {
    margin: "8px 0 0",
    color: "var(--text-secondary)",
    lineHeight: 1.55,
    fontWeight: 700,
  },
  accordionList: {
    maxWidth: 760,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  qaCard: {
    borderRadius: 20,
    background: "#ffffff",
    overflow: "hidden",
    boxShadow: "0 10px 24px rgba(33,33,33,0.06)",
  },
  questionButton: {
    width: "100%",
    minHeight: 58,
    border: "none",
    background: "transparent",
    display: "grid",
    gridTemplateColumns: "28px 1fr 24px",
    alignItems: "center",
    gap: 10,
    padding: "14px 16px",
    color: "var(--text-primary)",
    textAlign: "left",
    cursor: "pointer",
  },
  qaMark: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    background: "var(--brand-primary-soft)",
    color: "var(--brand-primary-deep)",
    display: "grid",
    placeItems: "center",
    fontWeight: 900,
  },
  questionText: {
    fontWeight: 900,
    lineHeight: 1.35,
  },
  chevron: {
    color: "var(--neutral-600)",
    fontSize: "1.2rem",
    transform: "rotate(0deg)",
    transition: "transform 180ms ease",
  },
  chevronOpen: {
    transform: "rotate(180deg)",
  },
  answerWrap: {
    overflow: "hidden",
    transition: "max-height 220ms ease",
  },
  answerInner: {
    display: "grid",
    gridTemplateColumns: "28px 1fr",
    gap: 10,
    padding: "0 16px 16px",
  },
  answerMark: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    background: "var(--brand-secondary-soft)",
    color: "var(--text-primary)",
    display: "grid",
    placeItems: "center",
    fontWeight: 900,
  },
  answerList: {
    margin: 0,
    paddingLeft: 18,
    color: "var(--neutral-700)",
    lineHeight: 1.55,
    fontWeight: 650,
  },
  answerItem: {
    marginBottom: 5,
  },
};
