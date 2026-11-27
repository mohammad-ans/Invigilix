import React, { useLayoutEffect, useRef, useState } from "react";

const names = { available: "Available", upcoming: "Upcoming", completed: "Completed" };

export default function RegisterIndex({ sections, onRead }) {
  const strip = useRef(null);
  const [position, setPosition] = useState(0);
  useLayoutEffect(() => {
    const list = strip.current.parentElement;
    const entries = Array.from(list.querySelectorAll(".dv-entry"));
    let frame;
    function measure() {
      frame = 0;
      if (!entries.length) return;
      // Read at the upper third of the screen, extending to the last card on short pages.
      const guide = Math.max(strip.current.offsetHeight + 10, window.innerHeight * .32);
      const first = entries[0].getBoundingClientRect().top + window.scrollY;
      const last = entries.at(-1).getBoundingClientRect().top + window.scrollY;
      const start = Math.max(0, first - guide);
      const end = Math.min(document.documentElement.scrollHeight - window.innerHeight, last - guide);
      const progress = end > start ? Math.max(0, Math.min(1, (window.scrollY - start) / (end - start))) : 0;
      const readingLine = first + progress * (last - first) - window.scrollY;
      let low = 0, high = entries.length - 1;
      while (low < high) {
        const mid = Math.ceil((low + high) / 2);
        if (entries[mid].getBoundingClientRect().top <= readingLine + 1) low = mid;
        else high = mid - 1;
      }
      // Keep a deliberate keyboard or pointer jump on the requested heading
      // until it scrolls behind the index or leaves the reading band.
      const target = document.activeElement;
      if (list.contains(target) && target.matches(".dv-group-head h2:target")) {
        const heading = target.getBoundingClientRect();
        const atEnd = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 1;
        if (heading.bottom > strip.current.getBoundingClientRect().bottom && heading.top <= (atEnd ? window.innerHeight : guide)) {
          low = entries.indexOf(target.closest(".dv-group").querySelector(".dv-entry"));
        }
      }
      setPosition(low);
      onRead(entries[low].dataset.examId);
    }
    function queue() {
      if (!frame) frame = requestAnimationFrame(measure);
    }
    measure();
    const observer = new ResizeObserver(queue);
    observer.observe(list);
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    list.addEventListener("focusin", queue);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("scroll", queue);
      window.removeEventListener("resize", queue);
      list.removeEventListener("focusin", queue);
    };
  }, [sections, onRead]);

  const exams = sections.flatMap(section => section.entries);
  const current = Math.min(position, exams.length - 1);
  const activeTab = sections.findIndex(section => section.group === exams[current].status);
  const number = n => String(n).padStart(2, "0");
  return (
    <nav ref={strip} className="dv-register-index" aria-label="Exam register sections">
      <span className="dv-counter" aria-label={`Exam ${current + 1} of ${exams.length}`}>
        <span className="dv-counter-window" aria-hidden="true"><b key={current}>{number(current + 1)}</b></span>
        <small aria-hidden="true">/ {number(exams.length)}</small>
      </span>
      <div className="dv-index-tabs" style={{ "--tabs": sections.length, "--tab": activeTab }}>
        {sections.map(({ group }, index) => (
          <a key={group} href={`#register-${group}`} aria-current={index === activeTab ? "location" : undefined}>
            {names[group]}
          </a>
        ))}
      </div>
    </nav>
  );
}
