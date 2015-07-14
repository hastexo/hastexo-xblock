/* Javascript for ViaductXBlock. */
function ViaductXBlock(runtime, element) {
  $(function ($) {
    GateOne.init({
      url: 'https://127.0.0.1',
      embedded: true,
      style: {
        'background-color': 'rgba(0, 0, 0, 0.85)',
        'box-shadow': '.5em .5em .5em black',
        'margin-bottom': '0.5em'
      }
    });

    GateOne.Base.superSandbox("GateOne.MyModule", ["GateOne.Terminal"], function(window, undefined) {
      var container = GateOne.Utils.getNode('#container');
      GateOne.Events.on('terminal:new_terminal', function(term) {
        GateOne.Terminal.disableScrollback(term);
      });
      window.setTimeout(function() {
        GateOne.Terminal.newTerminal(null, null, container);
      }, 50);
    });
  });
}
