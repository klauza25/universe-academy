/* Notifications flottantes du tableau de bord.

   Le gabarit pose les cartes déjà traduites : ce fichier n'invente aucun texte, il
   les fait glisser, les efface après un délai et joue un son court. Le son reste
   une intention du navigateur — aucun bruit n'est autorisé avant le premier geste
   sur la page. La notification d'une page fraîchement chargée est donc mise en
   attente et jouée au premier clic ou à la première touche, sans s'empiler. */
(function () {
    'use strict';

    const CLE_SON = 'ua-son';
    const MAXI = 5;
    const DUREE = {
        success: 7000,
        info: 8000,
        warning: 10000,
        error: 12000,
        danger: 12000,
    };
    const NOTES = {
        success: [[660, 0], [880, 0.12]],
        info: [[560, 0]],
        warning: [[520, 0], [400, 0.14]],
        error: [[420, 0], [300, 0.16]],
    };

    function sonSouhaite() {
        try { return localStorage.getItem(CLE_SON) !== 'off'; } catch (erreur) { return true; }
    }

    function memoriserSon(actif) {
        try { localStorage.setItem(CLE_SON, actif ? 'on' : 'off'); } catch (erreur) { /* navigation privée */ }
    }

    function niveauDe(toast) {
        const classe = ((toast.className || '').match(/ua-toast--([a-z]+)/) || [])[1];
        return NOTES[classe] ? classe : 'info';
    }

    // -- Le son ------------------------------------------------------------
    let contexte = null;
    let enAttente = null;

    function contexteAudio() {
        const Fabrique = window.AudioContext || window.webkitAudioContext;
        if (!Fabrique) { return null; }
        if (!contexte) {
            try { contexte = new Fabrique(); } catch (erreur) { return null; }
        }
        return contexte;
    }

    function emboiter(ctx, niveau, decalage) {
        NOTES[niveau].forEach(function (note) {
            const oscillateur = ctx.createOscillator();
            const volume = ctx.createGain();
            const depart = ctx.currentTime + decalage + note[1];
            oscillateur.type = 'sine';
            oscillateur.frequency.value = note[0];
            volume.gain.setValueAtTime(0.0001, depart);
            volume.gain.exponentialRampToValueAtTime(0.14, depart + 0.02);
            volume.gain.exponentialRampToValueAtTime(0.0001, depart + 0.16);
            oscillateur.connect(volume);
            volume.connect(ctx.destination);
            oscillateur.start(depart);
            oscillateur.stop(depart + 0.18);
        });
    }

    function viderAttente() {
        if (enAttente === null || !contexte || contexte.state !== 'running') { return; }
        const niveau = enAttente;
        enAttente = null;
        if (sonSouhaite()) { emboiter(contexte, niveau, 0); }
    }

    function jouer(niveau) {
        if (!sonSouhaite()) { return; }
        const ctx = contexteAudio();
        if (!ctx) { return; }
        if (ctx.state === 'running') { emboiter(ctx, niveau, 0); return; }
        enAttente = niveau;
        ctx.resume().then(viderAttente, function () { /* le geste suffira */ });
    }

    ['pointerdown', 'keydown'].forEach(function (evenement) {
        window.addEventListener(evenement, viderAttente, { passive: true });
    });

    // -- Les cartes --------------------------------------------------------
    function armerPile() {
        const racine = document.getElementById('ua-toasts');
        if (racine) { racine.classList.add('is-arme'); }
        return racine;
    }

    function disparaitre(toast) {
        if (!toast.parentNode) { return; }
        toast.classList.add('is-en-sortie');
        window.setTimeout(function () { toast.remove(); }, 300);
    }

    function montrer(toast) {
        window.requestAnimationFrame(function () {
            window.requestAnimationFrame(function () { toast.classList.add('is-en-place'); });
        });
        const bouton = toast.querySelector('.ua-toast-fermer');
        if (bouton) { bouton.addEventListener('click', function () { disparaitre(toast); }); }
        window.setTimeout(function () { disparaitre(toast); }, DUREE[niveauDe(toast)] || DUREE.info);
    }

    function basculerSon() {
        const actif = !sonSouhaite();
        memoriserSon(actif);
        document.documentElement.dataset.son = actif ? 'on' : 'off';
        const bouton = document.getElementById('ua-son-btn');
        if (bouton) { bouton.setAttribute('aria-pressed', actif ? 'true' : 'false'); }
        if (actif) { jouer('info'); }
    }

    let pile = armerPile();

    document.addEventListener('DOMContentLoaded', function () {
        const bouton = document.getElementById('ua-son-btn');
        if (bouton) {
            bouton.setAttribute('aria-pressed', sonSouhaite() ? 'true' : 'false');
            bouton.addEventListener('click', basculerSon);
        }

        pile = pile || armerPile();
        if (!pile) { return; }
        while (pile.children.length > MAXI) { pile.firstElementChild.remove(); }
        const toasts = Array.prototype.slice.call(pile.children);
        toasts.forEach(montrer);
        if (toasts.length) { jouer(niveauDe(toasts[toasts.length - 1])); }

        // Le panneau de rappel se ferme au clic dehors ou à l'Échap, comme le
        // menu latéral ; son ouverture reste possible sans JavaScript.
        const cloche = document.getElementById('ua-cloche');
        if (cloche) {
            document.addEventListener('click', function (event) {
                if (cloche.open && !cloche.contains(event.target)) cloche.open = false;
            });
            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') cloche.open = false;
            });
        }
    });
})();
