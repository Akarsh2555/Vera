import { useEffect, useState } from "react";

type RetroChartProps = {
  merchantId: string;
};

// Generates a pseudo-random percentage based on a string seed
function getSeededPercentage(seed: string, offset: number) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = seed.charCodeAt(i) + ((hash << 5) - hash);
  }
  hash = Math.abs(hash + offset);
  return 30 + (hash % 65); // Returns between 30% and 95%
}

export function RetroChart({ merchantId }: RetroChartProps) {
  const [animated, setAnimated] = useState(false);

  // Re-trigger the animation when merchant changes
  useEffect(() => {
    setAnimated(false);
    const timer = setTimeout(() => setAnimated(true), 50);
    return () => clearTimeout(timer);
  }, [merchantId]);

  if (!merchantId) return null;

  const metrics = [
    { label: "CONVERSION_PROB", value: getSeededPercentage(merchantId, 1) },
    { label: "UPLIFT_POTENTIAL", value: getSeededPercentage(merchantId, 2) },
    { label: "RESPONSE_RATE", value: getSeededPercentage(merchantId, 3) },
  ];

  return (
    <div className="retro-chart">
      {metrics.map((m, i) => (
        <div key={i} className="chart-row">
          <div className="chart-label">
            {m.label} <span className="chart-value">{m.value}%</span>
          </div>
          <div className="chart-bar-bg">
            <div 
              className="chart-bar-fill" 
              style={{ width: animated ? `${m.value}%` : "0%" }}
            ></div>
          </div>
        </div>
      ))}
    </div>
  );
}
