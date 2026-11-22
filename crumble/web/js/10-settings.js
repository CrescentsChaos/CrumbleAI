/* ---------- settings tab ---------- */
const SET = [['Realism', [
    ['realism', 'chk', 'Realism rules', 'Every prompt tells the character to talk like a real person: contractions, opinions, moods, no assistant-speak, no repeated openings.'],
    ['natural', 'sel', 'Speech naturalness', [[0, 'Off'], [1, 'Subtle'], [2, 'Natural'], [3, 'Messy']], 'Fillers, self-corrections, trailing off, tangents.'],
    ['timeaware', 'chk', 'Time awareness', 'The character knows how long it has been since you last spoke. If the story never says what time it is, it follows your real clock (the story always wins when it names a time).'],
    ['track', 'chk', 'Emotions and memory', 'After each reply the character updates its mood, how it feels about you, and remembers facts about you. Long chats are summarised automatically.'],
    ['thoughts', 'chk', 'Show inner thoughts', 'A private thought under each message (needs Emotions and memory).'],
    ['nudge', 'sel', 'Initiative', [[0, 'Off'], [1, 'After 1 min of silence'], [3, 'After 3 min'], [10, 'After 10 min']], 'The character follows up on its own if you go quiet (at most twice in a row).']]],
['Memory', [
    ['mem', 'chk', 'Hierarchical memory', 'Four layers: short-term (the scene), episodic (what happened), semantic (lasting facts) and emotional (how it felt). Each reply gets only the few memories that matter for what you just said, ranked by relevance, recency and importance. Needs Emotions and memory to learn new ones.'],
    ['memDepth', 'sel', 'How much to recall', [['light', 'Light (about 4 memories)'], ['standard', 'Standard (about 7)'], ['deep', 'Deep (about 10, notices more moments)']], 'More depth uses more of the context window.'],
    ['memLearn', 'chk', 'Write memories after important moments', 'After a gift, promise, fight, confession or \"remember this\", one extra small model call writes the episode and how the character felt. Turn off to only keep facts.']]],
['Story engine', [
    ['story', 'chk', 'Living world', 'Replaces the old fight system. Time matters, every character has a daily routine, the weather and the hour change how they feel, small things happen around you, and people joke and feel instead of just answering.'],
    ['storyRoutines', 'chk', 'Daily routines', 'Characters sleep, work, eat, get tired and have places to be. Write a “Daily routine” on the character sheet, or it is guessed from their occupation.'],
    ['storyWeather', 'sel', 'Weather', [['dynamic', 'The day has its own weather (unless the story says otherwise)'], ['story', 'Only what the story says']], 'Weather follows the season, builds over the day and changes how people feel and what they do.'],
    ['storyEvents', 'sel', 'Things happening around you', [['off', 'Off'], ['rare', 'Rare'], ['normal', 'Now and then'], ['lively', 'Lively']], 'A bus passing, a kettle clicking off, thunder. Never during sad, tender or dangerous moments.'],
    ['storyWildlife', 'sel', 'Wildlife encounters', [['off', 'Off'], ['rare', 'Rare'], ['normal', 'Now and then'], ['lively', 'Lively']], 'Real animals from data/animals/Animals.json turn up where they live (forest, jungle, desert, shore, open sea, river, a basement...) and an encounter plays out over a few messages. Never starts in a sad or tender moment. Not used in Texting or Voice call.'],
    ['storyScare', 'sel', 'How scary', [['gentle', 'Gentle: wonder and mischief, no real danger'], ['some', 'Some scares: wonder, fun, close calls and the odd terror'], ['lots', 'Dark: more stand-offs and terror']], 'Animals are as dangerous as they really are. Night, and scenarios that sound like horror or survival, make frights more likely.'],
    ['storyHumor', 'sel', 'Humour', [['auto', 'As written on the sheet'], ['more', 'More jokes and banter'], ['less', 'Fewer jokes']], ''],
    ['storyEndings', 'chk', 'Not every line ends in a question', 'Replies rarely end by asking something; the character states, reacts, teases, trails off or just does something.']]],
['Roleplay engine', [
    ['rp', 'sel', 'Action engine', [['auto', 'Auto: detect actions and resolve them'], ['manual', 'Manual: only the action buttons'], ['off', 'Off: plain chat']], 'No dice and no fight system: conflict is story. Skill attempts (persuade, sneak, aid...) are judged from your stats and the skills you describe under “About you”. Wounds and sickness last and heal with time and care; the dead stay dead unless someone brings them back. Every outcome is shown, and you can ignore it.'],
    ['diff', 'sel', 'Difficulty', [['easy', 'Easy'], ['normal', 'Normal'], ['hard', 'Hard']], ''],
    ['romance', 'chk', 'Romance system', 'Slow-burn romance with stages, pacing and consequences.'],
    ['tone', 'sel', 'Romance tone', [['sweet', 'Sweet (kisses at most)'], ['steamy', 'Steamy, tasteful (fades to black)']], ''],
    ['intimacy', 'chk', 'Intimacy system', 'Physical comfort and intimacy progression alongside romance. Only applies to adult (18+) characters.'],
    ['intimLevel', 'sel', 'Intimacy level', [['fade', 'Fade to black (PG)'], ['suggestive', 'Suggestive (sensual, implies acts)'], ['moderate', 'Moderate (literary, emotional scenes)'], ['explicit', 'Explicit (fully uninhibited, 18+ only)']], 'Content ceiling for physical intimacy. Minors are strictly excluded.'],
    ['intimPacing', 'sel', 'Intimacy pacing', [['slow', 'Slow burn'], ['natural', 'Natural'], ['fast', 'Fast']], 'How quickly physical comfort escalates.']]],
['Out of character (OOC)', [
    ['oocReply', 'sel', 'Storyteller replies', [['all', 'Reply to every OOC message'], ['discuss', 'Only reply when discussing (notes apply silently)']], 'Press the IC / OOC button (or Alt+O) to talk to the storyteller instead of the characters, or start one message with (( . The characters never hear OOC messages. Corrections, setting changes and directions become author notes you can see and remove in the Memory tab.']]],
['Replies and sound', [
    ['stream', 'chk', 'Show replies as they are written', 'Text appears while the model is still generating, so you never wait for a whole reply first. Turn off to wait and have it typed out instead.'],
    ['quick', 'chk', 'Quick replies', 'A reply is re-rolled at most once, and only for real mistakes (assistant-speak, writing your lines, naming a wrong fact). Turn off to also re-roll for style, repeats and mood. Better polish, slower.'],
    ['typing', 'sel', 'Typing animation', [['instant', 'Instant'], ['fast', 'Fast'], ['normal', 'Normal'], ['slow', 'Slow']], 'Only used when replies are not shown as they are written. Click a message or press Esc to skip.'],
    ['typos', 'chk', 'Typing mistakes in texting mode', 'Now and then a typo appears and gets corrected, like a real person on a phone.'],
    ['stamps', 'chk', 'Timestamps and read receipts', ''], ['sound', 'chk', 'Message sounds', ''], ['tts', 'chk', 'Read replies aloud', ''],
    ['voice', 'voice', 'Voice'], ['rate', 'rng', 'Speech rate', [.6, 1.6, .05]]]],
['Personality engine', [
    ['pers', 'chk', 'Personality engine', 'Keeps each character consistent: traits read from the sheet, reactions that depend on who they are, and moods that move the way they would.'],
    ['persDepth', 'sel', 'How much to tell the model', [['light', 'Light'], ['standard', 'Standard'], ['deep', 'Deep (adds an end-of-prompt reminder)']], 'More depth uses more of the context window.'],
    ['persDyn', 'chk', 'Personality-shaped mood', 'Mood and affection changes are bounded and coloured by temperament: a stoic does not flip to fury, and a grudge fades slowly.'],
    ['persCanon', 'chk', 'Remember what they say about themselves', 'Durable things the character states (job, likes, promises) are kept and checked so they do not contradict themselves.'],
    ['persGuard', 'chk', 'Consistency guard', 'A reply that sounds off (assistant-speak, wrong register, broken rules) is re-rolled, up to twice. Costs extra generation time when it triggers.'],
    ['persScore', 'chk', 'Show consistency score', 'A small badge next to each reply.']]],
['Appearance', [['theme2', 'themebtn', 'App theme', 'Used by every chat that has no style of its own. To style one chat, open the palette in its header: theme, accent, backdrop, font, bubbles and more.'], ['fs', 'rng', 'Text size', [12, 22, 1]]]]];
const PD = {
    temperature: 'Higher is more creative and less predictable.', top_p: 'Nucleus sampling cut-off.', top_k: 'Only consider the K likeliest tokens.', min_p: 'Drops very unlikely tokens.',
    repeat_penalty: 'Discourages repeating words.', presence_penalty: 'Nudges toward new topics.', frequency_penalty: 'Reduces repeated words.',
    max_tokens: 'Hard cap for one reply. Replies are asked to be shorter than this and are never left half-finished.', seed: '-1 picks a random seed.'
};
function renderSettings() {
    let h = '';
    for (const [sec, items] of SET) {
        h += `<details open><summary>${sec}</summary>`;
        for (const [k, t, l, o, hint] of items) {
            const hn = t == 'sel' || t == 'rng' ? hint : o;
            if (t == 'chk') h += `<label class=chk><input type=checkbox data-u=${k} ${U[k] ? 'checked' : ''}><span>${l}${hn ? `<small>${hn}</small>` : ''}</span></label>`;
            else if (t == 'sel') h += `<label>${l}</label><select data-u=${k}>${o.map(([v, x]) => `<option value="${v}" ${String(U[k]) == String(v) ? 'selected' : ''}>${x}</option>`).join('')}</select>${hn ? `<div class=small>${hn}</div>` : ''}`;
            else if (t == 'rng') h += `<label>${l}: <b>${U[k]}</b></label><input type=range data-u=${k} min=${o[0]} max=${o[1]} step=${o[2]} value=${U[k]}>`;
            else if (t == 'themebtn') h += `<label>${l}</label><button class=thbtn id=appTheme>${themeSw(U.theme2 || legacyT())}<span>${esc((PRE[(U.theme2 || legacyT()).p] || PRE.cocoa).n)}${U.theme2 && (U.theme2.ac || U.theme2.hue != null) ? ' (customised)' : ''}</span><span class=sp></span>${ico('chev')}</button><div class=small>${o}</div>`;
            else if (t == 'voice') h += `<label>${l}</label><select data-u=voice><option value="">(default)</option>${(window.speechSynthesis ? speechSynthesis.getVoices() : []).map(v => `<option ${v.name == U.voice ? 'selected' : ''}>${esc(v.name)}</option>`).join('')}</select>`
        }
        h += '</details>'
    }
    if (S.role != 'guest') h += `<details open><summary>Generation</summary>${Object.entries(P).map(([k, v]) => typeof v == 'boolean' ?
        `<label class=chk><input type=checkbox data-p=${k} ${v ? 'checked' : ''}><span>Fold the greeting into the system prompt<small>For models whose template rejects an assistant-first chat.</small></span></label>` :
        `<label>${k}${PD[k] ? ' - ' + PD[k] : ''}</label><input type=number step=any data-p=${k} value=${v}>`).join('')}</details>`;
    $('#sform').innerHTML = h;
    const at_ = $('#appTheme'); if (at_) at_.onclick = () => openStudio('app')
}
$('#sform').oninput = $('#sform').onchange = e => {
    const t = e.target, k = t.dataset.u, p = t.dataset.p;
    if (p) { P[p] = t.type == 'checkbox' ? t.checked : +t.value; persist(); return } if (!k) return;
    U[k] = t.type == 'checkbox' ? t.checked : typeof D[k] == 'number' ? +t.value : t.value; if (t.type == 'range') t.previousElementSibling.querySelector('b').textContent = t.value;
    persist(); applyUI(); if (['think', 'thoughts', 'stamps', 'track', 'rp', 'romance', 'intimacy', 'persScore'].includes(k)) { draw() }
};
function applyUI() { applyTheme(null, true); pills() }
if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => { if (S) renderSettings() };
