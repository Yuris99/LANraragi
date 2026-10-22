(function (root) {
  'use strict';
  const core = {
    nextTrack(tracks, id, mode) {
      if (mode !== 'all') return null;
      const index = tracks.findIndex(t => t.id === id);
      return index < 0 ? null : tracks[index + 1] || null;
    },
    activeCues(cues, time, delay) {
      const adjusted = time - delay; // Positive delay makes the caption appear later.
      return cues.filter(cue => cue.start <= adjusted && adjusted < cue.end).map(cue => cue.text).join('\n');
    },
    formatTime(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
      seconds = Math.floor(seconds);
      const minutes = Math.floor(seconds / 60);
      return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
    },
    move(tracks, id, delta) {
      const result = [...tracks], index = result.findIndex(t => t.id === id), to = index + delta;
      if (index < 0 || to < 0 || to >= result.length) return result;
      [result[index], result[to]] = [result[to], result[index]];
      return result;
    }
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = core;
  else root.PlayerCore = core;
})(typeof window !== 'undefined' ? window : globalThis);
