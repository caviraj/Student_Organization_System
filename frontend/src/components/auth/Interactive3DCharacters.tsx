import { useEffect, useRef, useState } from 'react';

interface Interactive3DCharactersProps {
  isPasswordActive: boolean;
}

export function Interactive3DCharacters({ isPasswordActive }: Interactive3DCharactersProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 200, y: 150 });
  const [isBlinking, setIsBlinking] = useState(false);

  // Natural occasional blink animation when eyes are open
  useEffect(() => {
    if (isPasswordActive) return;
    const interval = setInterval(() => {
      setIsBlinking(true);
      setTimeout(() => setIsBlinking(false), 180);
    }, 4000);
    return () => clearInterval(interval);
  }, [isPasswordActive]);

  // Track mouse coordinates across the entire window
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      setMousePos({ x, y });
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // Helper to calculate pupil offset towards the mouse
  const calculateEyeOffset = (eyeCenterX: number, eyeCenterY: number, maxRadius = 5.5) => {
    if (isPasswordActive || isBlinking) {
      return { x: 0, y: 0 };
    }
    const dx = mousePos.x - eyeCenterX;
    const dy = mousePos.y - eyeCenterY;
    const distance = Math.hypot(dx, dy);
    if (distance === 0) return { x: 0, y: 0 };
    const factor = Math.min(distance * 0.035, maxRadius) / distance;
    return {
      x: dx * factor,
      y: dy * factor,
    };
  };

  // Subtle 3D tilt of the character group
  const width = containerRef.current?.clientWidth || 400;
  const height = containerRef.current?.clientHeight || 450;
  const normX = Math.max(-1, Math.min(1, (mousePos.x - width / 2) / (width / 2)));
  const normY = Math.max(-1, Math.min(1, (mousePos.y - height / 2) / (height / 2)));
  const tiltX = -normY * 6; // degrees
  const tiltY = normX * 8; // degrees

  // Coordinates of eye centers in SVG viewBox (0 0 380 400)
  // 1. Blue Character Eyes
  const blueEyeL = calculateEyeOffset(135, 205, 5.5);
  const blueEyeR = calculateEyeOffset(165, 205, 5.5);

  // 2. Black Character Eyes
  const blackEyeL = calculateEyeOffset(195, 235, 5.0);
  const blackEyeR = calculateEyeOffset(218, 235, 5.0);

  // 3. Yellow Character Eyes
  const yellowEyeL = calculateEyeOffset(250, 260, 4.0);
  const yellowEyeR = calculateEyeOffset(275, 260, 4.0);

  // 4. Orange Character Eyes
  const orangeEyeL = calculateEyeOffset(145, 325, 4.5);
  const orangeEyeR = calculateEyeOffset(175, 325, 4.5);

  const eyesClosed = isPasswordActive || isBlinking;

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full min-h-[380px] sm:min-h-[460px] flex flex-col justify-between p-6 sm:p-8 select-none overflow-hidden"
      style={{
        perspective: '1000px',
      }}
    >
      {/* Top Header Tags matching user image */}
      <div className="relative z-10 flex items-center justify-between w-full">
        <div className="flex items-center gap-2 text-[11px] font-bold tracking-wider text-slate-500 uppercase">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shadow-xs" />
          <span>Campus AI Security</span>
        </div>
        <div className="px-3 py-1 rounded-full text-[11px] font-semibold text-slate-600 bg-white/80 backdrop-blur-xs border border-white/60 shadow-xs flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          Interactive 3D
        </div>
      </div>

      {/* 3D Toy Characters Cluster */}
      <div
        className="relative flex-1 flex items-end justify-center w-full transition-transform duration-200 ease-out mt-auto"
        style={{
          transform: `rotateX(${tiltX}deg) rotateY(${tiltY}deg)`,
          transformStyle: 'preserve-3d',
        }}
      >
        <svg
          viewBox="0 0 380 400"
          className="w-full max-w-[340px] sm:max-w-[370px] h-auto drop-shadow-xl overflow-visible"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* Subtle 3D Gradients */}
            <linearGradient id="blueToyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#4F8DF7" />
              <stop offset="100%" stopColor="#2563EB" />
            </linearGradient>

            <linearGradient id="blackToyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#2E333D" />
              <stop offset="100%" stopColor="#11151D" />
            </linearGradient>

            <linearGradient id="yellowToyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FBBF24" />
              <stop offset="100%" stopColor="#EAB308" />
            </linearGradient>

            <linearGradient id="orangeToyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FB923C" />
              <stop offset="100%" stopColor="#EA580C" />
            </linearGradient>

            {/* Soft contact shadows */}
            <filter id="softShadow" x="-10%" y="-10%" width="120%" height="130%">
              <feDropShadow dx="0" dy="8" stdDeviation="6" floodOpacity="0.18" floodColor="#0f172a" />
            </filter>
          </defs>

          {/* ================= CHARACTER 2: BLACK TOY (Behind / Center-Right) ================= */}
          <g className="transition-transform duration-300 ease-out" filter="url(#softShadow)">
            {/* Black capsule body */}
            <rect
              x="180"
              y="180"
              width="62"
              height="180"
              rx="28"
              fill="url(#blackToyGrad)"
              className="transition-all duration-300"
            />
            {/* 3D Highlight edge */}
            <rect
              x="182"
              y="182"
              width="58"
              height="176"
              rx="26"
              fill="none"
              stroke="rgba(255,255,255,0.12)"
              strokeWidth="2"
            />

            {/* Eyes of Black Character */}
            {eyesClosed ? (
              // Closed eyes when password active / blinking
              <g className="transition-all duration-200">
                <path
                  d="M 190 238 Q 195 243 200 238"
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                <path
                  d="M 213 238 Q 218 243 223 238"
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
              </g>
            ) : (
              // Open eyes following mouse
              <g className="transition-all duration-100 ease-out">
                {/* Left Eye */}
                <circle cx="195" cy="235" r="7.5" fill="#ffffff" />
                <circle
                  cx={195 + blackEyeL.x}
                  cy={235 + blackEyeL.y}
                  r="4"
                  fill="#111827"
                  className="transition-transform duration-75"
                />
                <circle cx={195 + blackEyeL.x + 1} cy={235 + blackEyeL.y - 1} r="1.3" fill="#ffffff" />

                {/* Right Eye */}
                <circle cx="218" cy="235" r="7.5" fill="#ffffff" />
                <circle
                  cx={218 + blackEyeR.x}
                  cy={235 + blackEyeR.y}
                  r="4"
                  fill="#111827"
                  className="transition-transform duration-75"
                />
                <circle cx={218 + blackEyeR.x + 1} cy={235 + blackEyeR.y - 1} r="1.3" fill="#ffffff" />
              </g>
            )}
          </g>

          {/* ================= CHARACTER 1: BLUE TOY (Tall Rectangle / Left) ================= */}
          <g className="transition-transform duration-300 ease-out" filter="url(#softShadow)">
            {/* Blue tall body */}
            <rect
              x="105"
              y="135"
              width="88"
              height="225"
              rx="18"
              fill="url(#blueToyGrad)"
            />
            {/* Top highlight for 3D volume */}
            <rect
              x="107"
              y="137"
              width="84"
              height="221"
              rx="16"
              fill="none"
              stroke="rgba(255,255,255,0.22)"
              strokeWidth="2"
            />

            {/* Eyes of Blue Toy */}
            {eyesClosed ? (
              // Closed curved happy eyes
              <g className="transition-all duration-200">
                <path
                  d="M 128 206 Q 135 212 142 206"
                  fill="none"
                  stroke="#1E3A8A"
                  strokeWidth="3.2"
                  strokeLinecap="round"
                />
                <path
                  d="M 158 206 Q 165 212 172 206"
                  fill="none"
                  stroke="#1E3A8A"
                  strokeWidth="3.2"
                  strokeLinecap="round"
                />
              </g>
            ) : (
              // Open large white eyes tracking cursor
              <g className="transition-all duration-100 ease-out">
                {/* Left Eye */}
                <circle cx="135" cy="205" r="9" fill="#ffffff" />
                <circle
                  cx={135 + blueEyeL.x}
                  cy={205 + blueEyeL.y}
                  r="4.8"
                  fill="#1E293B"
                  className="transition-transform duration-75"
                />
                <circle cx={135 + blueEyeL.x + 1.2} cy={205 + blueEyeL.y - 1.2} r="1.6" fill="#ffffff" />

                {/* Right Eye */}
                <circle cx="165" cy="205" r="9" fill="#ffffff" />
                <circle
                  cx={165 + blueEyeR.x}
                  cy={205 + blueEyeR.y}
                  r="4.8"
                  fill="#1E293B"
                  className="transition-transform duration-75"
                />
                <circle cx={165 + blueEyeR.x + 1.2} cy={205 + blueEyeR.y - 1.2} r="1.6" fill="#ffffff" />
              </g>
            )}

            {/* Mouth of Blue Toy (cute subtle smile) */}
            <path
              d="M 144 227 Q 150 233 156 227"
              fill="none"
              stroke="#1E3A8A"
              strokeWidth="2.8"
              strokeLinecap="round"
            />
          </g>

          {/* ================= CHARACTER 3: YELLOW TOY (Right Arch) ================= */}
          <g className="transition-transform duration-300 ease-out" filter="url(#softShadow)">
            {/* Yellow pill arch */}
            <rect
              x="234"
              y="215"
              width="68"
              height="145"
              rx="32"
              fill="url(#yellowToyGrad)"
            />
            {/* Highlight outline */}
            <rect
              x="236"
              y="217"
              width="64"
              height="141"
              rx="30"
              fill="none"
              stroke="rgba(255,255,255,0.28)"
              strokeWidth="2"
            />

            {/* Eyes of Yellow Toy */}
            {eyesClosed ? (
              // Closed slit/line eyes
              <g className="transition-all duration-200">
                <line x1="246" y1="260" x2="254" y2="260" stroke="#78350F" strokeWidth="3" strokeLinecap="round" />
                <line x1="271" y1="260" x2="279" y2="260" stroke="#78350F" strokeWidth="3" strokeLinecap="round" />
              </g>
            ) : (
              // Small cute dot eyes tracking mouse
              <g className="transition-all duration-100 ease-out">
                <circle
                  cx={250 + yellowEyeL.x}
                  cy={260 + yellowEyeL.y}
                  r="3.5"
                  fill="#78350F"
                  className="transition-transform duration-75"
                />
                <circle
                  cx={275 + yellowEyeR.x}
                  cy={260 + yellowEyeR.y}
                  r="3.5"
                  fill="#78350F"
                  className="transition-transform duration-75"
                />
              </g>
            )}

            {/* Flat line mouth */}
            <line
              x1="244"
              y1="285"
              x2="270"
              y2="285"
              stroke="#78350F"
              strokeWidth="3.2"
              strokeLinecap="round"
            />
          </g>

          {/* ================= CHARACTER 4: ORANGE TOY (Front Dome Mound) ================= */}
          <g className="transition-transform duration-300 ease-out" filter="url(#softShadow)">
            {/* Orange dome shape: flat bottom, rounded top */}
            <path
              d="M 100 360 C 100 295 220 295 220 360 Z"
              fill="url(#orangeToyGrad)"
            />
            {/* Specular top highlight */}
            <path
              d="M 105 358 C 108 300 212 300 215 358"
              fill="none"
              stroke="rgba(255,255,255,0.25)"
              strokeWidth="2.5"
            />

            {/* Eyes of Orange Toy */}
            {eyesClosed ? (
              // Closed smiling curve eyes
              <g className="transition-all duration-200">
                <path
                  d="M 140 326 Q 145 322 150 326"
                  fill="none"
                  stroke="#7C2D12"
                  strokeWidth="2.8"
                  strokeLinecap="round"
                />
                <path
                  d="M 170 326 Q 175 322 180 326"
                  fill="none"
                  stroke="#7C2D12"
                  strokeWidth="2.8"
                  strokeLinecap="round"
                />
              </g>
            ) : (
              // Dot eyes tracking mouse
              <g className="transition-all duration-100 ease-out">
                <circle
                  cx={145 + orangeEyeL.x}
                  cy={325 + orangeEyeL.y}
                  r="3.4"
                  fill="#7C2D12"
                  className="transition-transform duration-75"
                />
                <circle
                  cx={175 + orangeEyeR.x}
                  cy={325 + orangeEyeR.y}
                  r="3.4"
                  fill="#7C2D12"
                  className="transition-transform duration-75"
                />
              </g>
            )}

            {/* Friendly smile */}
            <path
              d="M 156 339 Q 160 343 164 339"
              fill="none"
              stroke="#7C2D12"
              strokeWidth="2.6"
              strokeLinecap="round"
            />
          </g>
        </svg>
      </div>

      {/* Subtle status indicator at bottom of left panel */}
      <div className="relative z-10 text-center pt-2">
        <p className="text-[11px] font-medium text-slate-400">
          {isPasswordActive ? (
            <span className="text-amber-600 font-semibold inline-flex items-center gap-1 animate-in fade-in">
              🙈 Characters are looking away while you enter password
            </span>
          ) : (
            <span className="text-slate-400 inline-flex items-center gap-1">
              Move cursor to interact &bull; Eyes follow your cursor
            </span>
          )}
        </p>
      </div>
    </div>
  );
}
