/* Dessin des graphiques de tableau de bord.

   core/graphiques.py prépare les séries et traduit déjà chaque libellé à la langue
   de la page : ce fichier n'invente aucun texte, il ne fait que peindre. Les couleurs
   viennent des mêmes jetons CSS que les cartes, si bien qu'un changement de thème
   redessine tout avec les teintes lisibles sur le fond choisi. */
(function () {
    'use strict';

    function jetons() {
        const calcule = getComputedStyle(document.documentElement);
        const lire = function (nom) { return calcule.getPropertyValue(nom).trim(); };
        return {
            teinte: function (nom) { return lire('--ua-tone-' + nom + '-fg') || lire('--ua-brand'); },
            encre: lire('--ua-ink'),
            discreto: lire('--ua-muted'),
            ligne: lire('--ua-line'),
            fond: lire('--ua-surface'),
        };
    }

    function avecAlpha(hex, alpha) {
        const corps = String(hex).replace('#', '');
        const developpe = corps.length === 3
            ? corps.split('').map(function (c) { return c + c; }).join('')
            : corps;
        const nombre = parseInt(developpe.slice(0, 6), 16);
        if (isNaN(nombre)) { return hex; }
        return 'rgba(' + ((nombre >> 16) & 255) + ',' + ((nombre >> 8) & 255) +
            ',' + (nombre & 255) + ',' + alpha + ')';
    }

    function construire(canevas, donnees) {
        const j = jetons();
        const langue = document.documentElement.lang || 'fr';
        const pleine = new Intl.NumberFormat(langue);
        const courte = new Intl.NumberFormat(langue, {
            notation: 'compact', maximumFractionDigits: 1,
        });
        const fcfa = donnees.unite === 'fcfa';
        const horizontal = donnees.horizontal === true;
        const axeCategorie = horizontal ? 'y' : 'x';
        const axeValeur = horizontal ? 'x' : 'y';

        const axes = {};
        axes[axeCategorie] = {
            grid: { display: false },
            border: { display: false },
            ticks: { color: j.discreto, font: { size: 11 } },
        };
        axes[axeValeur] = {
            beginAtZero: true,
            grid: { color: j.ligne },
            border: { display: false },
            ticks: {
                color: j.discreto,
                font: { size: 11 },
                callback: function (v) { return fcfa ? courte.format(v) : v; },
            },
        };

        const series = (donnees.series || []).map(function (s) {
            const couleur = j.teinte(s.couleur);
            const courbe = s.type === 'line';
            const pourCent = s.axe === 'secondaire';
            if (pourCent) {
                axes.secondaire = {
                    position: 'right',
                    beginAtZero: true,
                    max: 100,
                    grid: { display: false },
                    border: { display: false },
                    ticks: {
                        color: j.discreto,
                        font: { size: 11 },
                        callback: function (v) { return v + ' %'; },
                    },
                };
            }
            const jeu = {
                label: s.nom,
                data: s.valeurs,
                type: courbe ? 'line' : donnees.type,
                backgroundColor: courbe ? 'transparent' : avecAlpha(couleur, 0.75),
                borderColor: couleur,
                pointBackgroundColor: couleur,
                pointRadius: courbe ? 3 : 0,
                borderWidth: courbe ? 2 : 0,
                borderRadius: courbe ? 0 : 6,
                tension: 0.35,
                fill: false,
                order: courbe ? 0 : 1,
                _unite: fcfa ? 'fcfa' : (pourCent ? 'pourcent' : 'simple'),
            };
            // Chart.js choisit lui-même les axes quand indexAxis vaut 'y' :
            // imposer un identifiant d'axe inversé lui ferait lire une barre
            // horizontale sur un axe catégoriel linéaire.
            if (pourCent) { jeu.yAxisID = 'secondaire'; }
            return jeu;
        });

        return new window.Chart(canevas, {
            data: { labels: donnees.labels, datasets: series },
            options: {
                indexAxis: horizontal ? 'y' : 'x',
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        display: series.length > 1,
                        position: 'bottom',
                        labels: {
                            color: j.encre, usePointStyle: true,
                            boxWidth: 8, boxHeight: 8, font: { size: 11 },
                        },
                    },
                    tooltip: {
                        backgroundColor: j.fond,
                        titleColor: j.encre,
                        bodyColor: j.encre,
                        borderColor: j.ligne,
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: function (contexte) {
                                const valeur = horizontal
                                    ? contexte.parsed.x : contexte.parsed.y;
                                const suite = contexte.dataset._unite === 'fcfa'
                                    ? ' FCFA'
                                    : (contexte.dataset._unite === 'pourcent' ? ' %' : '');
                                return ' ' + contexte.dataset.label + ' : ' +
                                    pleine.format(valeur) + suite;
                            },
                        },
                    },
                },
                scales: axes,
            },
        });
    }

    function peindre() {
        if (!window.Chart) { return; }
        window.Chart.defaults.font.family =
            getComputedStyle(document.body).fontFamily || 'inherit';
        document.querySelectorAll('canvas[data-chart-source]').forEach(function (canevas) {
            const hote = document.getElementById(canevas.dataset.chartSource);
            if (!hote) { return; }
            let donnees;
            try { donnees = JSON.parse(hote.textContent); } catch (erreur) { return; }
            const existant = window.Chart.getChart(canevas);
            if (existant) { existant.destroy(); }
            construire(canevas, donnees);
        });
    }

    function demarrer() {
        peindre();
        new MutationObserver(peindre).observe(document.documentElement, {
            attributes: true, attributeFilter: ['data-theme'],
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', demarrer);
    } else {
        demarrer();
    }
})();
