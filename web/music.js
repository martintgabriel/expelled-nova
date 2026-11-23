// Background music and beach waves (spec 017): generated right here with the Web Audio API.
// No audio files, no library: every mood is a few soft chords plus sparse random notes, and
// the waves are filtered noise whose volume swells slowly.
//
// This module knows nothing about the game. main.js picks the mood from the state (only
// from `phase` and `lights_on`, which every player receives alike) and tells this module how
// close the own character is to the sea; music.js only plays it.
//
// It never makes an audio context of its own: Sound.onUnlock() (sound.js) hands over the
// shared one and its master gain once the first tap or key press has created them. So the
// volume slider scales the music too, and until then (or without Web Audio at all) every
// call below only remembers what was asked for, silently.
//
// Loaded after sound.js and before main.js (index.html); main.js is the only file calling it.

"use strict";

const Music = (() => {
  const MUSIC_VOLUME = 0.25; // the one knob for the music, relative to the master gain
  const WAVES_VOLUME = 0.6; // the waves at the water's edge, relative to the music
  const STORAGE_KEY = "expelled-nova-music";
  const CROSSFADE = 0.5; // setTargetAtTime time constant: about 1.5 s to fade over
  const FADE_OUT = 0.33; // to silence ("off", a hidden tab): about 1 s
  const SCHEDULE_EVERY_MS = 200; // how often the scheduler runs
  const LOOKAHEAD = 1; // seconds of music it plans ahead each time

  // A note number as on a piano keyboard (60 = middle C) to its frequency in Hz.
  const hz = (note) => 440 * 2 ** ((note - 69) / 12);

  // Each mood: a chord progression (note numbers), how long each chord lasts, the lowpass
  // filter, and the pentatonic scale the sparse random notes come from.
  const MOODS = {
    // Waiting in the lobby: calm and a bit brighter (C, Am, F, G).
    lobby: {
      chords: [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]],
      chordSeconds: 6,
      filter: 1800,
      timbre: "triangle",
      scale: [72, 74, 76, 79, 81],
      noteEvery: 1.5,
      noteChance: 0.45,
    },
    // A round: quieter and more open (Am, F, Dm, Em).
    playing: {
      chords: [[57, 60, 64], [53, 57, 60], [50, 53, 57], [52, 55, 59]],
      chordSeconds: 7,
      filter: 1100,
      timbre: "sine",
      scale: [69, 72, 74, 76, 79],
      noteEvery: 2,
      noteChance: 0.35,
    },
    // Lights out: lower, darker and slower.
    dark: {
      chords: [[45, 48, 52], [41, 44, 48], [38, 41, 45]],
      chordSeconds: 9,
      filter: 500,
      timbre: "sine",
      scale: [57, 60, 62, 64, 67],
      noteEvery: 3,
      noteChance: 0.2,
    },
  };

  let ctx = null; // the shared context, once sound.js has created it
  let musicGain = null; // MUSIC_VOLUME, into sound.js's master gain
  let wanted = "off"; // the mood main.js asked for last
  let on = loadOn(); // the music switch
  let layer = null; // the mood playing now: {name, gain, filter, nextChord, chordIndex, nextNote}
  let timer = null; // the scheduler's setInterval, only while a mood plays
  let wavesGain = null;
  let beach = 0; // 0 (far from the sea) to 1 (at the water)
  let wavesTarget = 0;

  function loadOn() {
    try {
      return localStorage.getItem(STORAGE_KEY) !== "0";
    } catch {
      return true; // storage unavailable: music on, the default
    }
  }

  function saveOn(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch {
      // storage unavailable: the choice just does not survive a reload
    }
  }

  // --- One mood = one layer: its own filter and fade, so two can crossfade ----------------

  function newLayer(name) {
    const gain = ctx.createGain();
    gain.gain.value = 0;
    gain.gain.setTargetAtTime(1, ctx.currentTime, CROSSFADE); // fade in
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = MOODS[name].filter;
    filter.connect(gain).connect(musicGain);
    const start = ctx.currentTime + 0.05;
    return { name, gain, filter, nextChord: start, chordIndex: 0, nextNote: start + 2 };
  }

  function fadeOut(old, timeConstant) {
    old.gain.gain.setTargetAtTime(0, ctx.currentTime, timeConstant);
    // Long after the fade: cut it off, notes still ringing on it included.
    setTimeout(() => old.gain.disconnect(), 8000);
  }

  // A soft chord tone: slow attack, held for the chord, slow release into the next chord.
  function pad(note, start, seconds, mood) {
    const attack = 2;
    const release = 3;
    const osc = ctx.createOscillator();
    osc.type = mood.timbre;
    osc.frequency.value = hz(note);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0, start);
    env.gain.linearRampToValueAtTime(0.15, start + attack);
    env.gain.setValueAtTime(0.15, start + seconds);
    env.gain.linearRampToValueAtTime(0, start + seconds + release);
    osc.connect(env).connect(layer.filter);
    osc.start(start);
    osc.stop(start + seconds + release + 0.1);
  }

  // One sparse note: a quick, soft start and a long fade.
  function sparkle(note, start, mood) {
    const osc = ctx.createOscillator();
    osc.type = mood.timbre;
    osc.frequency.value = hz(note);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0, start);
    env.gain.linearRampToValueAtTime(0.1, start + 0.05);
    env.gain.exponentialRampToValueAtTime(0.001, start + 2.5);
    osc.connect(env).connect(layer.filter);
    osc.start(start);
    osc.stop(start + 2.6);
  }

  // The lookahead scheduler: every SCHEDULE_EVERY_MS, plan whatever starts within the next
  // LOOKAHEAD seconds on the audio clock (ctx.currentTime). The notes then play exactly on
  // time even if the browser's main thread is busy for a moment.
  function schedule() {
    if (!layer) return;
    const mood = MOODS[layer.name];
    const until = ctx.currentTime + LOOKAHEAD;
    while (layer.nextChord < until) {
      const chord = mood.chords[layer.chordIndex % mood.chords.length];
      for (const note of chord) pad(note, layer.nextChord, mood.chordSeconds, mood);
      layer.chordIndex++;
      layer.nextChord += mood.chordSeconds;
    }
    while (layer.nextNote < until) {
      if (Math.random() < mood.noteChance) {
        const note = mood.scale[Math.floor(Math.random() * mood.scale.length)];
        sparkle(note, layer.nextNote, mood);
      }
      layer.nextNote += mood.noteEvery;
    }
  }

  // What should play right now: the wanted mood, unless the switch is off or the tab hidden.
  function apply() {
    if (!ctx) return;
    const name = on && !document.hidden ? wanted : "off";
    const current = layer ? layer.name : "off";
    if (name !== current) {
      if (layer) fadeOut(layer, name === "off" ? FADE_OUT : CROSSFADE);
      layer = name === "off" ? null : newLayer(name);
    }
    if (layer && !timer) {
      timer = setInterval(schedule, SCHEDULE_EVERY_MS);
      schedule();
    } else if (!layer && timer) {
      clearInterval(timer);
      timer = null;
    }
    updateWaves();
  }

  // --- Sea waves: looped noise, lowpass-filtered, swelling slowly --------------------------

  function startWaves() {
    const length = ctx.sampleRate * 2; // two seconds of noise, looped (noise has no seam)
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 450;
    // The swell: a very slow oscillator moves the volume between 0.2 and 1 (one wave ~8 s).
    const swell = ctx.createGain();
    swell.gain.value = 0.6;
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.12;
    const depth = ctx.createGain();
    depth.gain.value = 0.4;
    lfo.connect(depth).connect(swell.gain);
    wavesGain = ctx.createGain();
    wavesGain.gain.value = 0;
    source.connect(filter).connect(swell).connect(wavesGain).connect(musicGain);
    source.start();
    lfo.start();
  }

  function updateWaves() {
    if (!wavesGain) return;
    const inRound = wanted === "playing" || wanted === "dark";
    // Spec 035: the waves play in the lobby too, and there quietly anywhere on the campus.
    const inLobby = wanted === "lobby";
    const closeness = inLobby ? Math.max(beach, 0.25) : beach;
    const target = on && !document.hidden && (inRound || inLobby) ? closeness * WAVES_VOLUME : 0;
    if (Math.abs(target - wavesTarget) < 0.01) return; // called every tick: only real changes
    wavesTarget = target;
    wavesGain.gain.setTargetAtTime(target, ctx.currentTime, 0.6);
  }

  // --- Start once sound.js has the context; pause while the tab is hidden -----------------

  Sound.onUnlock((sharedCtx, master) => {
    ctx = sharedCtx;
    musicGain = ctx.createGain();
    musicGain.gain.value = MUSIC_VOLUME;
    musicGain.connect(master);
    startWaves();
    apply(); // the mood asked for before the first gesture starts now
  });
  document.addEventListener("visibilitychange", apply);

  function setMood(name) {
    if (name !== "off" && !(name in MOODS)) return;
    wanted = name;
    apply();
  }

  function setBeach(closeness) {
    beach = Math.min(1, Math.max(0, Number(closeness) || 0));
    updateWaves();
  }

  function setOn(value) {
    on = Boolean(value);
    saveOn(on);
    apply();
  }

  return {
    setMood,
    setBeach,
    isOn: () => on,
    setOn,
    toggle: () => setOn(!on),
  };
})();
