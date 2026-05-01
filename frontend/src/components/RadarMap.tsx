import { useEffect, useState } from "react";

type RadarMapProps = {
  city?: string;
  locality?: string;
};

export function RadarMap({ city, locality }: RadarMapProps) {
  const [dots, setDots] = useState<{x: number, y: number}[]>([]);

  useEffect(() => {
    // Generate a pseudo-random dot location based on locality string
    if (locality) {
      let hash = 0;
      for (let i = 0; i < locality.length; i++) {
        hash = locality.charCodeAt(i) + ((hash << 5) - hash);
      }
      const x = 20 + (Math.abs(hash) % 60); // 20% to 80%
      const y = 20 + (Math.abs(hash >> 3) % 60);
      setDots([{ x, y }]);
    } else {
      setDots([]);
    }
  }, [locality]);

  return (
    <div className="radar-container">
      <div className="radar-screen">
        <div className="radar-sweep"></div>
        <div className="radar-grid"></div>
        <div className="radar-crosshair"></div>
        
        {dots.map((dot, i) => (
          <div 
            key={i} 
            className="radar-blip" 
            style={{ left: `${dot.x}%`, top: `${dot.y}%` }}
          >
            <div className="blip-pulse"></div>
            <div className="blip-label">{locality}<br/>{city}</div>
          </div>
        ))}
      </div>
      <div className="radar-status">
        <span className="blinking-cursor"></span> TRACKING MERCHANT GEOLOCATION...
      </div>
    </div>
  );
}
