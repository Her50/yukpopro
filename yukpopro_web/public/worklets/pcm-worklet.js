// PCM16 downsampler AudioWorklet for YukpoTranslate Live.
// Accumulates ~150 ms of mono PCM at the AudioContext sample rate,
// downsamples it to 16 kHz linear PCM16 little-endian, and posts it
// back to the main thread as a Transferable ArrayBuffer.
class PCMWorkletProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this._targetRate = 16000;
    this._srcRate = sampleRate; // Global from AudioWorkletGlobalScope
    this._ratio = this._srcRate / this._targetRate;
    this._buf = [];
    // Flush when we have ~150 ms of source audio (at src rate)
    this._flushAtFrames = Math.floor(this._srcRate * 0.15);
    this._accumulated = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    // Copy this block
    const block = new Float32Array(channel.length);
    block.set(channel);
    this._buf.push(block);
    this._accumulated += block.length;

    if (this._accumulated >= this._flushAtFrames) {
      this._flush();
    }
    return true;
  }

  _flush() {
    const totalIn = this._accumulated;
    const merged = new Float32Array(totalIn);
    let offset = 0;
    for (const b of this._buf) {
      merged.set(b, offset);
      offset += b.length;
    }
    this._buf = [];
    this._accumulated = 0;

    const outLen = Math.floor(totalIn / this._ratio);
    const pcm16 = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * this._ratio;
      const lo = Math.floor(srcIdx);
      const hi = Math.min(lo + 1, totalIn - 1);
      const frac = srcIdx - lo;
      const sample = merged[lo] * (1 - frac) + merged[hi] * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      pcm16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    }
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
  }
}

registerProcessor("pcm-worklet", PCMWorkletProcessor);
