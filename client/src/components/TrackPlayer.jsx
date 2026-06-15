import { useState, useEffect, useRef } from 'react';

export default function TrackPlayer({ track, onPositionChange }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!playing) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    let i = index;
    intervalRef.current = setInterval(() => {
      if (i >= track.length - 1) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
        setPlaying(false);
        return;
      }
      i++;
      setIndex(i);
      onPositionChange(i);
    }, 200);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [playing]);

  function handleSlider(e) {
    const val = parseInt(e.target.value);
    setIndex(val);
    onPositionChange(val);
  }

  if (!track || track.length === 0) return null;

  const point = track[index];
  return (
    <div className="track-player">
      <div className="track-controls">
        <button onClick={() => setPlaying(!playing)}>{playing ? 'Pause' : 'Play'}</button>
        <input type="range" min={0} max={track.length - 1} value={index} onChange={handleSlider} />
        <span>{index + 1} / {track.length}</span>
      </div>
      {point && (
        <div className="track-info">
          <span>{new Date(point.timestamp).toLocaleString()}</span>
          <span>Speed: {point.speed ? `${point.speed.toFixed(1)} km/h` : 'N/A'}</span>
        </div>
      )}
    </div>
  );
}
