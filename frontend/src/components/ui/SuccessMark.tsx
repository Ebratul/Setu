/** Animated check in a soft success circle. Decorative; pair it with text. Motion is disabled by reduced-motion CSS. */
export function SuccessMark({ size = 20 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      data-testid="success-mark"
      className="anim-pop inline-flex shrink-0 items-center justify-center rounded-full bg-success text-white"
      style={{ width: size + 8, height: size + 8 }}
    >
      <svg
        viewBox="0 0 24 24"
        width={size}
        height={size}
        fill="none"
        stroke="currentColor"
        strokeWidth={2.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="anim-check"
        focusable="false"
      >
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
    </span>
  );
}
