class FamilyRecorder extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const channel = inputs[0]?.[0];
    if (channel) {
      const copy = new Float32Array(channel);
      this.port.postMessage(copy.buffer, [copy.buffer]);
    }
    for (const output of outputs) for (const channel of output) channel.fill(0);
    return true;
  }
}
registerProcessor("family-recorder", FamilyRecorder);
