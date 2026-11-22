// Sound effects (spec 016): every sound is generated right here with the Web Audio API.
// No audio files, no library: every effect below is a short oscillator tone or a burst of
// filtered noise, picked because together they can build everything the spec asks for
// (a footstep, a click, a chime, a gong, a buzz, even a paper rip) without a single sample.
//
// Browsers only allow audio after a user gesture, also on phones (spec 007): the shared
// AudioContext is created on the first pointer press or key press anywhere on the page,
// never on load. Until then (and if Web Audio does not exist at all) every Sound.play()
// call below is simply a no-op, so the game plays on exactly as before, just silent.
//
// Loaded before main.js (index.html), which is the only file that calls Sound.play(...).

"use strict";

const Sound = (() => {
  const MASTER_VOLUME = 0.22; // the one knob for every sound at once
  const MUTE_KEY = "expelled-nova-muted";

  let ctx = null;
  let master = null;
  let muted = loadMuted();

  function loadMuted() {
    try {
      return localStorage.getItem(MUTE_KEY) === "1";
    } catch {
      return false; // storage unavailable: sound on, same as a browser that never muted
    }
  }

  function saveMuted(value) {
    try {
      localStorage.setItem(MUTE_KEY, value ? "1" : "0");
    } catch {
      // storage unavailable: the choice just does not survive a reload
    }
  }

  // Created lazily, on the first gesture; calling it again only resumes a suspended
  // context (some browsers suspend it again after a long tab switch).
  function unlock() {
    if (ctx) {
      if (ctx.state === "suspended") ctx.resume();
      return;
    }
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return; // no Web Audio: ctx stays null, every play() below is a no-op
    ctx = new AudioCtx();
    master = ctx.createGain();
    master.gain.value = muted ? 0 : MASTER_VOLUME;
    master.connect(ctx.destination);
  }
  document.addEventListener("pointerdown", unlock, { once: true });
  document.addEventListener("keydown", unlock, { once: true });

  // --- Two primitives every effect below is built from ----------------------------------

  // A short tone: one oscillator with its own volume envelope (quick fade in, exponential
  // fade to silence), so notes never click at the edges or need to be stopped by hand.
  function tone(freq, duration, { type = "sine", gain = 1, delay = 0, slideTo = null } = {}) {
    if (!ctx) return;
    const start = ctx.currentTime + delay;
    const osc = ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, start);
    if (slideTo) osc.frequency.linearRampToValueAtTime(slideTo, start + duration);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0, start);
    env.gain.linearRampToValueAtTime(gain, start + 0.008);
    env.gain.exponentialRampToValueAtTime(0.001, start + duration);
    osc.connect(env).connect(master);
    osc.start(start);
    osc.stop(start + duration + 0.02);
  }

  // A burst of filtered noise: footsteps, paper, keys and buzzes are all this, only the
  // filter and the length differ.
  function noise(duration, { type = "lowpass", freq = 1000, q = 1, gain = 1, delay = 0 } = {}) {
    if (!ctx) return;
    const start = ctx.currentTime + delay;
    const length = Math.max(1, Math.round(ctx.sampleRate * duration));
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = freq;
    filter.Q.value = q;
    const env = ctx.createGain();
    env.gain.setValueAtTime(gain, start);
    env.gain.exponentialRampToValueAtTime(0.001, start + duration);
    source.connect(filter).connect(env).connect(master);
    source.start(start);
    source.stop(start + duration + 0.02);
  }

  // --- One effect per name main.js plays, each built from the two primitives above ------

  const EFFECTS = {
    // Own footsteps only (main.js never calls this for another player).
    footstep: () => noise(0.05, { type: "lowpass", freq: 300, gain: 0.5 }),
    // Buttons, action buttons, arrow cards, lobby and overlay buttons.
    click: () => tone(1100, 0.03, { type: "square", gain: 0.5 }),
    // Casting a vote (yours) and seeing another player's vote land (no identity in either).
    voteSelf: () => tone(900, 0.07, { type: "triangle", gain: 0.7 }),
    voteOther: () => tone(700, 0.05, { type: "sine", gain: 0.3 }),
    // The role reveal: one chord, identical for students and examiners.
    roleReveal: () => {
      for (const freq of [196, 233, 294]) tone(freq, 0.9, { type: "sawtooth", gain: 0.25 });
    },
    // A finished task (own, real or fake) versus one finished step of a multi-step one.
    taskDone: () => {
      tone(880, 0.12, { type: "sine", gain: 0.6 });
      tone(1320, 0.18, { type: "sine", gain: 0.6, delay: 0.1 });
    },
    taskStep: () => tone(1100, 0.1, { type: "sine", gain: 0.5 }),
    // A meeting starting: a school gong, for everyone.
    meetingChime: () => {
      for (const freq of [523, 784, 1046]) tone(freq, 1.4, { type: "sine", gain: 0.35 });
    },
    // Paper ripping: filtered noise, only for the examiner who expelled and the expelled.
    expel: () => noise(0.35, { type: "highpass", freq: 1500, q: 0.7, gain: 0.8 }),
    // The one shared "wrong answer" buzz, for any mini-game.
    error: () => tone(140, 0.18, { type: "sawtooth", gain: 0.5 }),
    // Mini-games (spec 012), one fitting sound each.
    ticketDing: () => tone(1400, 0.15, { type: "sine", gain: 0.6 }), // "now serving" beep
    cardAccept: () => {
      noise(0.05, { type: "bandpass", freq: 2500, q: 2, gain: 0.3 }); // the swipe
      tone(1500, 0.1, { type: "sine", gain: 0.5, delay: 0.05 }); // the accept beep
    },
    cableClick: () => tone(2000, 0.03, { type: "square", gain: 0.5 }), // plug clicks in
    seagullHit: () => {
      tone(1800, 0.08, { type: "sawtooth", gain: 0.3, slideTo: 2600 }); // the squawk
      noise(0.15, { type: "bandpass", freq: 1200, q: 1, gain: 0.3, delay: 0.05 }); // the whoosh
    },
    typingClick: () => noise(0.02, { type: "highpass", freq: 3000, gain: 0.3 }), // a keystroke
    paperRattle: () => noise(0.06, { type: "bandpass", freq: 900, q: 0.8, gain: 0.4 }), // a jam tap
  };

  function play(name) {
    if (muted || !ctx) return;
    const effect = EFFECTS[name];
    if (effect) effect();
  }

  function setMuted(value) {
    muted = Boolean(value);
    if (master) master.gain.value = muted ? 0 : MASTER_VOLUME;
    saveMuted(muted);
  }

  return {
    play,
    isMuted: () => muted,
    setMuted,
    toggleMute: () => setMuted(!muted),
  };
})();
