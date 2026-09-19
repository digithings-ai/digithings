/** Official-style crypto marks (BTC, ETH, SOL) for strategy cards and tearsheets. */

export type CryptoAsset = "btc" | "eth" | "sol";

const ASSET_SRC: Record<CryptoAsset, string> = {
  btc: "/assets/crypto/btc.svg",
  eth: "/assets/crypto/eth.svg",
  sol: "/assets/crypto/sol.svg",
};

const ASSET_LABEL: Record<CryptoAsset, string> = {
  btc: "Bitcoin",
  eth: "Ethereum",
  sol: "Solana",
};

export function resolveCryptoAsset(input: {
  strategy?: string;
  symbol?: string;
}): CryptoAsset | null {
  if (input.strategy) {
    if (input.strategy.startsWith("btc_")) return "btc";
    if (input.strategy.startsWith("eth_")) return "eth";
    if (input.strategy.startsWith("sol_")) return "sol";
  }
  if (input.symbol) {
    const base = input.symbol.split("-")[0]?.toUpperCase();
    if (base === "BTC") return "btc";
    if (base === "ETH") return "eth";
    if (base === "SOL") return "sol";
  }
  return null;
}

export function AssetLogo({
  asset,
  size = 28,
  className = "",
  title,
}: {
  asset: CryptoAsset;
  size?: number;
  className?: string;
  /** Accessible name; defaults to the asset name (Bitcoin, etc.). */
  title?: string;
}) {
  const label = title ?? ASSET_LABEL[asset];
  return (
    <img
      src={ASSET_SRC[asset]}
      alt=""
      width={size}
      height={size}
      className={`asset-logo asset-logo-${asset}${className ? ` ${className}` : ""}`}
      aria-hidden={title === ""}
      title={label}
    />
  );
}

/** Logo when asset is known; nothing rendered when it cannot be resolved. */
export function AssetLogoFor({
  strategy,
  symbol,
  size = 28,
  className = "",
}: {
  strategy?: string;
  symbol?: string;
  size?: number;
  className?: string;
}) {
  const asset = resolveCryptoAsset({ strategy, symbol });
  if (!asset) return null;
  return <AssetLogo asset={asset} size={size} className={className} />;
}
