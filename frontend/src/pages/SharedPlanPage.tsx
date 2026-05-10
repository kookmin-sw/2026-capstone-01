import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { useParams } from "react-router-dom";
import {
  BRAND,
  getPublicSharedPlan,
  type PlanDetailResponse,
  type PlanItemResponse,
} from "../api/aiPlanShared";

function groupItemsByDay(items: PlanItemResponse[]): Array<{
  dayNumber: number;
  items: PlanItemResponse[];
}> {
  const dayNumbers = Array.from(new Set(items.map((item) => item.day_number))).sort(
    (left, right) => left - right
  );

  return dayNumbers.map((dayNumber) => ({
    dayNumber,
    items: items
      .filter((item) => item.day_number === dayNumber)
      .sort((left, right) => left.position - right.position),
  }));
}

export default function PublicSharedPlanPage() {
  const { shareToken = "" } = useParams();
  const [plan, setPlan] = useState<PlanDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!shareToken) {
      setErrorMessage("Share token is missing.");
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setErrorMessage("");

    void getPublicSharedPlan(shareToken)
      .then((data) => {
        if (!cancelled) setPlan(data);
      })
      .catch((error) => {
        if (!cancelled) {
          setPlan(null);
          setErrorMessage(
            error instanceof Error ? error.message : "Failed to load shared plan."
          );
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [shareToken]);

  const dayGroups = useMemo(() => groupItemsByDay(plan?.items || []), [plan]);

  return (
    <div style={styles.page}>
      <main style={styles.shell}>
        <header style={styles.header}>
          <span style={styles.badge}>Shared Trip Plan</span>
          <h1 style={styles.title}>{plan?.title || "Shared Seoul Plan"}</h1>
          <p style={styles.copy}>
            This plan is visible to anyone with the share link. No login is required.
          </p>
          {plan ? (
            <div style={styles.metaRow}>
              <span>
                {dayGroups.length} day itinerary
              </span>
              <span>Updated {new Date(plan.updated_at).toLocaleString()}</span>
            </div>
          ) : null}
        </header>

        {isLoading ? (
          <section style={styles.stateCard}>Loading shared plan...</section>
        ) : errorMessage ? (
          <section style={styles.errorCard}>{errorMessage}</section>
        ) : !plan || dayGroups.length === 0 ? (
          <section style={styles.stateCard}>No places are available in this plan.</section>
        ) : (
          <div style={styles.dayStack}>
            {dayGroups.map((group, groupIndex) => (
              <section key={group.dayNumber} style={styles.daySection}>
                <div style={styles.dayHeader}>
                  <strong>Day {groupIndex + 1}</strong>
                  <span>{group.items.length} places</span>
                </div>
                <div style={styles.itemList}>
                  {group.items.map((item, index) => (
                    <article key={item.item_id} style={styles.itemCard}>
                      <div style={styles.itemIndex}>{index + 1}</div>
                      <div style={styles.itemBody}>
                        <div style={styles.itemTopRow}>
                          <strong style={styles.itemTitle}>{item.display_name}</strong>
                          {typeof item.rating === "number" ? (
                            <span style={styles.ratingBadge}>{item.rating.toFixed(1)}</span>
                          ) : null}
                        </div>
                        <p style={styles.address}>{item.address}</p>
                        <div style={styles.itemMeta}>
                          <span>{item.visit_time || "--:--"}</span>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "var(--app-viewport-height)",
    padding: "calc(22px + var(--app-safe-top)) 16px 22px",
    background: "linear-gradient(180deg, #f7ffff 0%, #fefdf7 100%)",
    fontFamily: '"Nunito", "Apple SD Gothic Neo", sans-serif',
  },
  shell: {
    maxWidth: 720,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  header: {
    padding: 22,
    borderRadius: 24,
    background: "#ffffff",
    border: "1px solid #dceeee",
    boxShadow: "0 12px 30px rgba(16, 34, 35, 0.06)",
  },
  badge: {
    display: "inline-flex",
    padding: "7px 10px",
    borderRadius: 999,
    background: "rgba(1,192,192,0.12)",
    color: BRAND,
    fontSize: 12,
    fontWeight: 900,
  },
  title: {
    margin: "14px 0 8px",
    color: "#102223",
    fontSize: 28,
    lineHeight: 1.15,
  },
  copy: {
    margin: 0,
    color: "#557071",
    fontSize: 14,
    lineHeight: 1.6,
  },
  metaRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 14,
    color: "#5d7576",
    fontSize: 12,
    fontWeight: 800,
  },
  stateCard: {
    padding: 22,
    borderRadius: 20,
    background: "#ffffff",
    border: "1px solid #dceeee",
    color: "#557071",
    textAlign: "center",
  },
  errorCard: {
    padding: 22,
    borderRadius: 20,
    background: "#fff8f8",
    border: "1px solid rgba(220,38,38,0.22)",
    color: "#b91c1c",
    fontWeight: 800,
    textAlign: "center",
  },
  dayStack: {
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  daySection: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  dayHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    color: "#102223",
    fontSize: 15,
    fontWeight: 900,
  },
  itemList: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  itemCard: {
    display: "grid",
    gridTemplateColumns: "34px 1fr",
    gap: 12,
    padding: 14,
    borderRadius: 18,
    background: "#ffffff",
    border: "1px solid #dceeee",
  },
  itemIndex: {
    width: 34,
    height: 34,
    borderRadius: 12,
    background: BRAND,
    color: "#ffffff",
    display: "grid",
    placeItems: "center",
    fontSize: 13,
    fontWeight: 900,
  },
  itemBody: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  itemTopRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
  },
  itemTitle: {
    color: "#102223",
    fontSize: 15,
    overflowWrap: "anywhere",
  },
  ratingBadge: {
    padding: "5px 8px",
    borderRadius: 999,
    background: "rgba(255,190,15,0.2)",
    color: "#7a5400",
    fontSize: 11,
    fontWeight: 900,
  },
  address: {
    margin: 0,
    color: BRAND,
    fontSize: 12,
    fontWeight: 800,
    lineHeight: 1.5,
  },
  itemMeta: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    color: "#5d7576",
    fontSize: 12,
    fontWeight: 800,
  },
};
