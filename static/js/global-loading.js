/* Écran de chargement global : visible au démarrage, puis à chaque navigation interne. */
(function () {
    var overlay = document.getElementById('ua-global-loading');
    if (!overlay) { return; }

    var pret = false;
    var securite = null;

    function masquer() {
        window.clearTimeout(securite);
        pret = true;
        overlay.classList.add('ua-global-loading--hidden');
    }

    function afficher() {
        if (!pret) { return; }
        pret = false;
        overlay.classList.remove('ua-global-loading--hidden');
        securite = window.setTimeout(masquer, 10000);
    }

    if (document.readyState === 'complete') {
        masquer();
    } else {
        window.addEventListener('load', masquer);
    }

    window.addEventListener('pageshow', function (event) {
        if (event.persisted) { masquer(); }
    });

    document.addEventListener('submit', function (event) {
        if (event.target && event.target !== overlay) { afficher(); }
    }, true);

    document.addEventListener('click', function (event) {
        if (event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        var cible = event.target && event.target.closest
            ? event.target.closest('a[href]')
            : null;
        if (!cible || cible.target === '_blank' || cible.hasAttribute('download') ||
            cible.dataset.noLoading !== undefined) {
            return;
        }
        var url = new URL(cible.href, window.location.href);
        if (url.origin !== window.location.origin) { return; }
        if (url.pathname === window.location.pathname &&
            url.search === window.location.search && url.hash) {
            return;
        }
        afficher();
    }, true);
})();
