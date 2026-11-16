/* Notifications flottantes du tableau de bord.

   Le gabarit pose les cartes déjà traduites : ce fichier n'invente aucun texte, il
   les fait glisser, les efface après un délai et signale les nouveaux événements. Le son reste
   une intention du navigateur — aucun bruit n'est autorisé avant le premier geste
   sur la page. La notification d'une page fraîchement chargée est donc mise en
   attente et jouée au premier clic ou à la première touche, sans s'empiler. */
(function () {
    'use strict';

    const CLE_SON = 'ua-son';
    const MAXI = 5;
    const DUREE = {
        success: 12000,
        info: 12000,
        warning: 12000,
        error: 12000,
        danger: 12000,
    };
    const DUREE_SONNERIE = 8000;
    const NOTES = {
        success: [784, 988, 1175, 988],
        info: [659, 784, 988, 784],
        warning: [587, 698, 880, 698],
        error: [523, 659, 784, 659],
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
    let sonnerieTimer = null;
    let sonnerieFin = 0;

    function contexteAudio() {
        const Fabrique = window.AudioContext || window.webkitAudioContext;
        if (!Fabrique) { return null; }
        if (!contexte) {
            try { contexte = new Fabrique(); } catch (erreur) { return null; }
        }
        return contexte;
    }

    function emboiter(ctx, niveau, decalage, index) {
        const fondamentales = NOTES[niveau];
        const frequence = fondamentales[index % fondamentales.length];
        [[1, 0.13], [2.76, 0.045], [5.4, 0.015]].forEach(function (partiel) {
            const oscillateur = ctx.createOscillator();
            const volume = ctx.createGain();
            const depart = ctx.currentTime + decalage;
            oscillateur.type = 'sine';
            oscillateur.frequency.value = frequence * partiel[0];
            volume.gain.setValueAtTime(0.0001, depart);
            volume.gain.exponentialRampToValueAtTime(partiel[1], depart + 0.025);
            volume.gain.exponentialRampToValueAtTime(0.0001, depart + 0.72);
            oscillateur.connect(volume);
            volume.connect(ctx.destination);
            oscillateur.start(depart);
            oscillateur.stop(depart + 0.74);
        });
    }

    function arreterSonnerie() {
        if (sonnerieTimer !== null) { window.clearTimeout(sonnerieTimer); }
        sonnerieTimer = null;
        sonnerieFin = 0;
    }

    function sonner(niveau, duree) {
        arreterSonnerie();
        sonnerieFin = Date.now() + duree;
        let index = 0;

        function repeter() {
            if (!sonSouhaite() || Date.now() >= sonnerieFin) {
                arreterSonnerie();
                return;
            }
            emboiter(contexte, niveau, 0, index);
            index += 1;
            sonnerieTimer = window.setTimeout(repeter, 900);
        }

        repeter();
    }

    function viderAttente() {
        if (enAttente === null || !contexte || contexte.state !== 'running') { return; }
        const demande = enAttente;
        enAttente = null;
        if (!sonSouhaite()) { return; }
        if (demande.duree) { sonner(demande.niveau, demande.duree); }
        else { emboiter(contexte, demande.niveau, 0, 0); }
    }

    function activerAudio() {
        if (!sonSouhaite()) { return; }
        const ctx = contexteAudio();
        if (!ctx || ctx.state === 'running') {
            viderAttente();
            return;
        }
        ctx.resume().then(viderAttente, function () { /* le navigateur peut bloquer l'audio */ });
    }

    function jouer(niveau, duree) {
        if (!sonSouhaite()) { return; }
        const ctx = contexteAudio();
        if (!ctx) { return; }
        if (ctx.state === 'running') {
            if (duree) { sonner(niveau, duree); }
            else { emboiter(ctx, niveau, 0, 0); }
            return;
        }
        enAttente = { niveau: niveau, duree: duree || 0 };
        ctx.resume().then(viderAttente, function () { /* le geste suffira */ });
    }

    ['pointerdown', 'keydown'].forEach(function (evenement) {
        window.addEventListener(evenement, activerAudio, { passive: true });
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
        if (!actif) {
            arreterSonnerie();
            enAttente = null;
        }
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
        if (pile) {
            while (pile.children.length > MAXI) { pile.firstElementChild.remove(); }
            const toasts = Array.prototype.slice.call(pile.children);
            toasts.forEach(montrer);
            if (toasts.length) { jouer(niveauDe(toasts[toasts.length - 1]), DUREE_SONNERIE); }
        }

        const cloche = document.getElementById('ua-cloche');
        if (cloche) {
            let curseur = cloche.dataset.eventCursor;
            const url = cloche.dataset.pollUrl;

            function actualiserCloche() {
                if (document.visibilityState !== 'visible') { return; }
                fetch(url, { credentials: 'same-origin', cache: 'no-store' })
                    .then(function (reponse) {
                        if (!reponse.ok) { throw new Error('HTTP ' + reponse.status); }
                        return reponse.json();
                    })
                    .then(function (etat) {
                        if (etat.event_cursor !== curseur) {
                            curseur = etat.event_cursor;
                            ajouterToast(cloche.dataset.eventMessage, cloche.dataset.closeLabel);
                            jouer('info', DUREE_SONNERIE);
                        }
                        actualiserContenuCloche(cloche, etat);
                        const pastille = cloche.querySelector('.ua-cloche-pastille');
                        if (pastille) {
                            pastille.textContent = etat.total;
                            pastille.hidden = !etat.total;
                        } else if (etat.total) {
                            const nouvellePastille = document.createElement('span');
                            nouvellePastille.className = 'ua-cloche-pastille';
                            nouvellePastille.textContent = etat.total;
                            cloche.querySelector('.ua-cloche-btn').appendChild(nouvellePastille);
                        }
                    })
                    .catch(function (erreur) {
                        console.error('Impossible de vérifier les notifications.', erreur);
                    });
            }

            window.setInterval(actualiserCloche, 8000);
        }

        // Le panneau de rappel se ferme au clic dehors ou à l'Échap, comme le
        // menu latéral ; son ouverture reste possible sans JavaScript.
        if (cloche) {
            document.addEventListener('click', function (event) {
                if (cloche.open && !cloche.contains(event.target)) cloche.open = false;
            });
            document.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') cloche.open = false;
            });
        }
    });

    function vider(element) {
        while (element.firstChild) { element.removeChild(element.firstChild); }
    }

    function actualiserContenuCloche(cloche, etat) {
        const sectionTaches = cloche.querySelector('#ua-cloche-tasks');
        const listeTaches = cloche.querySelector('#ua-cloche-liste');
        vider(listeTaches);
        etat.tasks.forEach(function (tache) {
            const ligne = document.createElement('li');
            const lien = document.createElement('a');
            const nom = document.createElement('span');
            const nombre = document.createElement('span');
            lien.href = tache.url;
            nom.className = 'ua-cloche-nom';
            nom.textContent = tache.name;
            nombre.className = 'ua-badge ua-badge-amber';
            nombre.textContent = tache.count;
            lien.appendChild(nom);
            lien.appendChild(nombre);
            ligne.appendChild(lien);
            listeTaches.appendChild(ligne);
        });
        sectionTaches.hidden = etat.tasks.length === 0;

        const sectionNotifications = cloche.querySelector('#ua-cloche-notifications');
        const listeNotifications = cloche.querySelector('#ua-cloche-fils');
        vider(listeNotifications);
        etat.notifications.forEach(function (notification) {
            const ligne = document.createElement('li');
            const titre = document.createElement('p');
            const message = document.createElement('p');
            const date = document.createElement('p');
            titre.className = 'ua-cloche-note-titre';
            titre.textContent = notification.title;
            message.className = 'ua-cloche-note-texte';
            message.textContent = notification.message;
            date.className = 'ua-cloche-note-date';
            date.textContent = notification.created_at;
            ligne.appendChild(titre);
            ligne.appendChild(message);
            ligne.appendChild(date);
            listeNotifications.appendChild(ligne);
        });
        sectionNotifications.hidden = etat.notifications.length === 0;
        const formLire = sectionNotifications.querySelector('form');
        if (formLire) { formLire.hidden = etat.notifications.length === 0; }
        cloche.querySelector('#ua-cloche-vide').hidden = etat.total > 0;
    }

    function ajouterToast(texte, libelleFermeture) {
        const racine = armerPile();
        if (!racine) { return; }
        while (racine.children.length >= MAXI) {
            racine.firstElementChild.remove();
        }
        const toast = document.createElement('div');
        const icone = document.createElement('span');
        const contenu = document.createElement('span');
        const bouton = document.createElement('button');
        toast.className = 'ua-toast ua-toast--info';
        icone.className = 'ua-toast-icone';
        icone.setAttribute('aria-hidden', 'true');
        icone.textContent = 'i';
        contenu.className = 'ua-toast-texte';
        contenu.textContent = texte;
        bouton.type = 'button';
        bouton.className = 'ua-toast-fermer';
        bouton.setAttribute('aria-label', libelleFermeture);
        bouton.textContent = '×';
        toast.appendChild(icone);
        toast.appendChild(contenu);
        toast.appendChild(bouton);
        racine.appendChild(toast);
        montrer(toast);
    }
})();
