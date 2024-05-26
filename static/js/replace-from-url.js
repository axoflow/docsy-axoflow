document.addEventListener('DOMContentLoaded', function() {

    // Get the URL parameter value
    const urlParams = new URLSearchParams(window.location.search);

    // Lookup table for product=value URLs
    const productLinks = {
        fortigate: 'fortigate',
        paloalto: 'paloalto',
        sonicwall: 'sonicwall',
        generic: 'generic',
      };

    if (urlParams.has('product')){
        console.log("Redirecting to product-specific syslog page");
        const replaceValue = urlParams.get('replace-address');
        const rootdir = `/syslog-collection/`
        // Lookup product-specific URL, and set productdir to the generic link if not found
        var productdir = productLinks[urlParams.get('product')] || 'generic'

        console.log('4', productdir)
        urlParams.delete('product');
        var url = window.location.href
        // Find the rootdir in the url and delete it and everything afterwards to get the base url, then re-add the rootdir, product dir, and other query params
        url = url.substring(0, url.indexOf(rootdir)) + rootdir + productdir + `/?` + urlParams; ;
        // console.log(url);
        window.location.href = url
    }

    // FIXME loop through URL parameters beginning with replace-, and replace the relevant placeholder
    if (urlParams.has('replace-address')){
        console.log("Replacing placeholder address");
        const replaceValue = urlParams.get('replace-address');
        // Identify the text to be replaced
        const textToReplace = '%axorouter-ip%';
        // console.log(textToReplace, replaceValue);
        // If the 'replace-address' parameter exists in the URL, replace the text
        // FIXME: if it doesn't exist, replace with a default, or optionally with one from the frontmatter
        const contentDiv = document.getElementsByClassName('td-content');
        const replacedText = textToReplace.replace(textToReplace, replaceValue);

        replaceRecursively(document.body, new RegExp(textToReplace, "g"), replaceValue);

    }
    if (urlParams.has('replace-port')){
        console.log("Replacing placeholder port");
        const replaceValue = urlParams.get('replace-port');
        // Identify the text to be replaced
        const textToReplace = '%axorouter-port%';
        // console.log(textToReplace, replaceValue);
        // If the 'replace-port' parameter exists in the URL, replace the text
        // FIXME: if it doesn't exist, replace with a default, or optionally with one from the frontmatter
        const contentDiv = document.getElementsByClassName('td-content');
        const replacedText = textToReplace.replace(textToReplace, replaceValue);

        replaceRecursively(document.body, new RegExp(textToReplace, "g"), replaceValue);

    }
});

function replaceRecursively(element, from, to) {
    if (element.childNodes.length) {
        element.childNodes.forEach(child => replaceRecursively(child, from, to));
    } else {
        const cont = element.textContent;
        if (cont) element.textContent = cont.replace(from, to);
    }
};

