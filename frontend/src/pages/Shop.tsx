/** Shop — every gift you can play Lucky Buy for. */

import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Empty, Screen, SectionTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { gg } from "@/lib/format";
import { haptics } from "@/lib/telegram";

export function ShopPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["shop"], queryFn: () => api.shop() });

  return (
    <Screen>
      <div className="stack" style={{ gap: 2 }}>
        <h1>Shop</h1>
        <p className="muted" style={{ fontSize: 14 }}>
          Pick a gift, pick your odds. The stake follows from both — win it and it lands in your
          inventory, where you can keep it or sell it back.
        </p>
      </div>

      <SectionTitle>Gifts</SectionTitle>

      {isLoading ? (
        <Skeleton height={132} count={3} />
      ) : !data?.gifts.length ? (
        <Empty glyph="◆" title="The shop is empty" />
      ) : (
        <div className="gift-grid">
          {data.gifts.map((gift) => (
            <button
              key={gift.code}
              className="gift-card"
              data-rarity={gift.rarity}
              onClick={() => {
                haptics.tap();
                navigate(`/shop/${gift.code}`);
              }}
            >
              <span className="gift-glyph">{gift.glyph}</span>
              <span className="gift-name">{gift.name}</span>
              <span className="gift-value">{gg(gift.gg_value)} GG</span>
              <span className={`faint rarity-${gift.rarity}`}>{gift.rarity}</span>
            </button>
          ))}
        </div>
      )}
    </Screen>
  );
}
