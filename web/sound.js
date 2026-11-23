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
  const VOLUME_KEY = "expelled-nova-volume"; // spec 020: the slider, 0-1, per browser

  let ctx = null;
  let master = null;
  let muted = loadMuted();
  let volume = loadVolume();
  const unlockCallbacks = []; // waiting for the context (spec 017: music.js)

  function loadMuted() {
    try {
      return localStorage.getItem(MUTE_KEY) === "1";
    } catch {
      return false; // storage unavailable: sound on, same as a browser that never muted
    }
  }

  function loadVolume() {
    try {
      const stored = localStorage.getItem(VOLUME_KEY);
      return stored === null ? 1 : clamp(Number(stored));
    } catch {
      return 1; // storage unavailable: full volume, same as a browser that never moved it
    }
  }

  function saveVolume(value) {
    try {
      localStorage.setItem(VOLUME_KEY, String(value));
    } catch {
      // storage unavailable: the choice just does not survive a reload
    }
  }

  function clamp(value) {
    return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 1;
  }

  // The master gain (spec 020): the slider scales the one MASTER_VOLUME constant.
  function gainValue() {
    return muted ? 0 : MASTER_VOLUME * volume;
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
    master.gain.value = gainValue();
    master.connect(ctx.destination);
    for (const callback of unlockCallbacks) callback(ctx, master);
    unlockCallbacks.length = 0;
  }
  document.addEventListener("pointerdown", unlock, { once: true });
  document.addEventListener("keydown", unlock, { once: true });

  // Spec 017: lets music.js share this one context and master gain instead of creating its
  // own, so the mute button silences music and effects together. The callback runs once the
  // context exists (right away if it already does); without Web Audio it never runs.
  function onUnlock(callback) {
    if (ctx) callback(ctx, master);
    else unlockCallbacks.push(callback);
  }

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

    // Spec 017: seven more, each heard by every player who receives the same event.
    // A report: an urgent two-tone alarm, on top of the meeting gong.
    reportAlarm: () => {
      for (let i = 0; i < 4; i++) {
        tone(i % 2 === 0 ? 880 : 660, 0.14, { type: "square", gain: 0.35, delay: i * 0.15 });
      }
    },
    // One of the last 5 seconds of voting.
    countdownTick: () => tone(1250, 0.04, { type: "triangle", gain: 0.4 }),
    // A vent hatch moving (climbing in or out), for everyone in sight of it.
    ventHatch: () => {
      noise(0.12, { type: "bandpass", freq: 700, q: 3, gain: 0.5 }); // the metal lid
      tone(190, 0.18, { type: "square", gain: 0.25 }); // the clank
      tone(470, 0.12, { type: "triangle", gain: 0.25, delay: 0.03 });
    },
    // The lights: a power-down slide and a power-up click.
    lightsOut: () => tone(440, 0.7, { type: "sawtooth", gain: 0.35, slideTo: 55 }),
    lightsOn: () => {
      noise(0.03, { type: "highpass", freq: 2500, gain: 0.5 }); // the switch
      tone(330, 0.3, { type: "triangle", gain: 0.4, delay: 0.03, slideTo: 990 }); // the hum
    },
    // Spec 020: the end of a round sounds by the winning side, the same for everyone.
    // Examiners win: three low, gloomy notes ("dun dun dun"), the last one long.
    examinersWin: () => {
      [[147, 0], [139, 0.45], [110, 0.9]].forEach(([freq, delay], i) => {
        tone(freq, i === 2 ? 1.6 : 0.4, { type: "sawtooth", gain: 0.4, delay });
        tone(freq / 2, i === 2 ? 1.6 : 0.4, { type: "sine", gain: 0.5, delay });
      });
    },
    // Students win: a rising "wheeey" slide, then a bright major chord.
    studentsWin: () => {
      tone(300, 0.7, { type: "triangle", gain: 0.5, slideTo: 1200 });
      tone(450, 0.7, { type: "sine", gain: 0.3, slideTo: 1800 });
      for (const freq of [784, 988, 1175, 1568]) tone(freq, 0.9, { type: "triangle", gain: 0.3, delay: 0.7 });
    },
    // Spec 020: under the "Expelled!" voice, a deep falling drop (also alone without speech).
    expelVoice: () => {
      tone(220, 0.6, { type: "sawtooth", gain: 0.35, slideTo: 55 });
      say("Expelled!");
    },
    // Spec 027: the security guard catching an expel, on top of the meeting gong. A rising
    // two-pulse siren, distinct from reportAlarm's flat two-tone buzz.
    securityAlarm: () => {
      tone(600, 0.22, { type: "sine", gain: 0.35, slideTo: 1100 });
      tone(600, 0.22, { type: "sine", gain: 0.3, slideTo: 1100, delay: 0.24 });
    },
  };

  // The browser's own speech synthesis (spec 020): no audio file. Deep and slow; quietly
  // does nothing when muted or when the browser has no speech synthesis.
  function say(text) {
    if (muted || volume === 0 || !("speechSynthesis" in window)) return;
    try {
      const line = new SpeechSynthesisUtterance(text);
      line.lang = "en-US";
      line.pitch = 0.1; // as deep as the voice goes
      line.rate = 0.75;
      line.volume = Math.min(1, volume);
      window.speechSynthesis.cancel(); // never queue up behind an older line
      window.speechSynthesis.speak(line);
    } catch {
      // speech synthesis failed: the drop tone above still played
    }
  }

  function play(name) {
    if (muted || !ctx) return;
    const effect = EFFECTS[name];
    if (effect) effect();
  }

  function setMuted(value) {
    muted = Boolean(value);
    if (master) master.gain.value = gainValue();
    saveMuted(muted);
  }

  // Spec 020: 0-1 from the slider. Moving it while muted unmutes; 0 counts as muted.
  function setVolume(value) {
    volume = clamp(Number(value));
    saveVolume(volume);
    if (volume > 0 && muted) setMuted(false);
    if (master) master.gain.value = gainValue();
  }

  return {
    onUnlock,
    play,
    isMuted: () => muted || volume === 0,
    setMuted,
    getVolume: () => volume,
    setVolume,
    toggleMute: () => setMuted(!muted),
  };
})();
