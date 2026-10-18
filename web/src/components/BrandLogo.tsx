export function BrandLogo() {
  return (
    <div className="brand-lockup" aria-label="ClearTrade">
      <svg className="brand-symbol" viewBox="0 0 40 40" aria-hidden="true">
        <defs>
          <linearGradient id="cleartrade-mark" x1="5" y1="4" x2="35" y2="36" gradientUnits="userSpaceOnUse">
            <stop stopColor="#B9F2C9" />
            <stop offset="1" stopColor="#4EBB8A" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="38" height="38" rx="13" fill="#183326" stroke="#47795A" />
        <path d="M11 14.5h8.2a5.8 5.8 0 1 1 0 11.6H11" fill="none" stroke="url(#cleartrade-mark)" strokeWidth="3.2" strokeLinecap="round" />
        <path d="M17.5 20.3h11" fill="none" stroke="#E5F7E9" strokeWidth="2.4" strokeLinecap="round" />
        <path d="m24.8 16.6 3.8 3.7-3.8 3.7" fill="none" stroke="#E5F7E9" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="brand-wordmark"><span>Clear</span><strong>Trade</strong></span>
    </div>
  );
}
