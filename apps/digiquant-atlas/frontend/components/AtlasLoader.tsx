export default function AtlasLoader(props: { fullScreen?: boolean }) {
  const { fullScreen = true } = props;

  return (
    <div className={fullScreen ? 'atlas-loader-screen' : 'atlas-loader-inline'}>
      <div className="atlas-loader">
        <div className="atlas-loader-logo" aria-hidden="true">
          <svg
            className="atlas-loader-mark"
            width="56"
            height="56"
            viewBox="0 0 48 48"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
            focusable="false"
          >
            <rect className="atlas-loader-bg" width="48" height="48" rx="10" />
            <path
              className="atlas-loader-stroke atlas-loader-stroke-1"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4.2774,32.5293a11.6485,11.6485,0,0,1,23.2219,1.32h0c0,3.2166.0022,11.6479.0022,11.6479"
            />
            <path
              className="atlas-loader-stroke atlas-loader-stroke-2"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3.3047,29.8574q-.0277-.4816-.0279-.97a16.61,16.61,0,1,1,33.2209,0v0c0,4.5869.0031,16.6095.0031,16.6095"
            />
            <circle
              className="atlas-loader-stroke atlas-loader-stroke-3"
              strokeWidth="2"
              cx="16.5007"
              cy="33.4992"
              r="5.0328"
            />
            <path
              className="atlas-loader-stroke atlas-loader-stroke-4"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M45.5,24A21.5,21.5,0,1,0,24,45.5H45.5Z"
            />
          </svg>
        </div>
      </div>
    </div>
  );
}

