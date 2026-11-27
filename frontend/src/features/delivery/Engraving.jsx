import React, { useEffect, useRef } from "react";

// Interlaced rose-engine curves, like the fine linework on printed admission tickets.
export default function Engraving() {
  const canvas = useRef(null);
  useEffect(() => {
    const plate = canvas.current;
    const ink = plate.getContext("2d");
    if (!ink) return;
    const center = plate.width / 2;
    const turn = Math.PI * 2;
    ink.clearRect(0, 0, plate.width, plate.height);
    ink.strokeStyle = getComputedStyle(plate).color;
    ink.lineWidth = 1.35;
    for (let strand = 0; strand < 22; strand++) {
      const phase = turn * strand / 22;
      ink.beginPath();
      for (let step = 0; step <= 720; step++) {
        const angle = turn * step / 720;
        const radius = center * (0.76 + 0.14 * Math.cos(9 * angle + phase)
          + 0.075 * Math.cos(5 * angle - phase));
        const x = center + radius * Math.cos(angle);
        const y = center + radius * Math.sin(angle);
        if (step === 0) ink.moveTo(x, y);
        else ink.lineTo(x, y);
      }
      ink.closePath();
      ink.stroke();
    }
  }, []);
  return <canvas className="dv-engraving" width="520" height="520" ref={canvas} aria-hidden="true" />;
}
