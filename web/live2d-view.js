/* Live2D 挂载：失败一律返回 null，调用方回退到静态图 */
(function () {
  const MODEL = '/live2d/' + encodeURIComponent('大肥鱼.model3.json');

  async function mount(container, opts) {
    if (!window.PIXI || !PIXI.live2d) return null;
    const w = container.clientWidth || 300;
    const h = container.clientHeight || 380;
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
    container.innerHTML = '';
    container.appendChild(canvas);

    const app = new PIXI.Application({
      view: canvas, width: w, height: h, backgroundAlpha: 0,
      antialias: true, autoDensity: true, resolution: window.devicePixelRatio || 1,
    });

    const model = await PIXI.live2d.Live2DModel.from(MODEL, { autoInteract: false });
    app.stage.addChild(model);

    const s = Math.min(w / model.width, h / model.height) * 1.02;
    model.scale.set(s);
    model.x = (w - model.width * s) / 2;
    model.y = h - model.height * s;

    let mouth = 0, idle = 0;
    app.ticker.add(function () {
      idle += 0.05;
      mouth *= 0.9;
      try {
        const core = model.internalModel.coreModel;
        core.setParameterValueById('ParamMouthOpenY', mouth);
        core.setParameterValueById('ParamAngleX', Math.sin(idle * 0.6) * 4);
        core.setParameterValueById('ParamAngleY', Math.cos(idle * 0.5) * 3);
      } catch (e) { }
    });

    return {
      kind: 'live2d',
      setColor: function () { },
      setViews: function () { },
      setVector: function () { },
      pulse: function (v) { mouth = Math.min(1, mouth + (v || 1)); },
      speak: function () { mouth = 1; },
      stopSpeaking: function () { mouth = 0; },
      resize: function () {
        const nw = container.clientWidth || w, nh = container.clientHeight || h;
        app.renderer.resize(nw, nh);
        const ns = Math.min(nw / model.width, nh / model.height) * 1.02;
        model.scale.set(ns);
        model.x = (nw - model.width * ns) / 2;
        model.y = nh - model.height * ns;
      },
      destroy: function () { try { app.destroy(true); } catch (e) { } },
    };
  }

  window.Live2DView = { mount: mount, model: MODEL };
})();
