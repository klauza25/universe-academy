(function () {
    'use strict';

    var banner = document.getElementById('cookie-consent');
    var settingsButton = document.getElementById('cookie-settings');
    if (!banner || !settingsButton) return;

    var storageKey = 'ua-cookie-consent-v1';
    var measurementId = banner.getAttribute('data-ga-id') || '';

    function loadAnalytics() {
        if (!/^G-[A-Z0-9]+$/.test(measurementId) || document.getElementById('ua-ga-script')) {
            return;
        }

        window.dataLayer = window.dataLayer || [];
        window.gtag = function () {
            window.dataLayer.push(arguments);
        };
        window.gtag('js', new Date());
        window.gtag('config', measurementId, {
            allow_google_signals: false,
            allow_ad_personalization_signals: false
        });

        var script = document.createElement('script');
        script.id = 'ua-ga-script';
        script.async = true;
        script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(measurementId);
        document.head.appendChild(script);
    }

    function showBanner() {
        banner.hidden = false;
        settingsButton.hidden = true;
    }

    function hideBanner() {
        banner.hidden = true;
        settingsButton.hidden = false;
    }

    var choice = null;
    try {
        choice = window.localStorage.getItem(storageKey);
    } catch (error) {
        showBanner();
    }

    if (choice === 'accepted') {
        hideBanner();
        loadAnalytics();
    } else if (choice === 'rejected') {
        hideBanner();
    } else {
        showBanner();
    }

    banner.addEventListener('click', function (event) {
        var button = event.target.closest('[data-cookie-choice]');
        if (!button) return;

        var accepted = button.getAttribute('data-cookie-choice') === 'accept';
        try {
            window.localStorage.setItem(storageKey, accepted ? 'accepted' : 'rejected');
        } catch (error) {
            // The current choice still applies to this page when storage is disabled.
        }

        hideBanner();
        if (accepted) loadAnalytics();
    });

    settingsButton.addEventListener('click', showBanner);
})();
