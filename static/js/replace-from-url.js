document.addEventListener('DOMContentLoaded', function() {

    // Get the URL parameter value
    const urlParams = new URLSearchParams(window.location.search);

    console.log(urlParams);

    if (urlParams.has('product')){
        console.log("Redirecting to product-specific syslog page");
        const replaceValue = urlParams.get('replace-ip');
        // FIXME create a lookup table for product=value to URL
        const rootdir = `syslog-collection/`
        const productdir = urlParams.get('product')
        urlParams.delete('product');
        window.location.href = rootdir + productdir + `/?` + urlParams;
    }

    // FIXME loop through URL parameters beginning with replace-, and replace the relevant placeholder
    if (urlParams.has('replace-ip')){
        console.log("Replacing placeholder IP");
        const replaceValue = urlParams.get('replace-ip');
        // Identify the text to be replaced
        const textToReplace = '%axorouter-ip%';
        // console.log(textToReplace, replaceValue);
        // If the 'replace-ip' parameter exists in the URL, replace the text
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

