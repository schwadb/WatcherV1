import { useState, useEffect, useRef, useCallback } from 'react';

export default function TrackPlayer({ track, onPositionChange }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const indexRef = useRef(index);
  indexRef.current = index;

  const advance = useCallback(() => {
    const next = indexRef.current + 1;
    if (next >= track.length) {
      setPlaying(false);
      return;
    }
    setIndex(next);
    onPositionChange(next);
  }, [track.length, onPositionChange]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(advance, 200);
    return () => clearInterval(id);
  }, [playing, advance]);

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
          <span>Speed: {point.speed != null ? `${point.speed.toFixed(1)} km/h` : 'N/A'}</span>
        </div>
      )}
    </div>
  );
}
