document.addEventListener('DOMContentLoaded', function() {
    // Identify the text to be replaced
    const textToReplace = '%placeholder-ip%';

    // Get the URL parameter value
    const urlParams = new URLSearchParams(window.location.search);

    // FIXME loop through URL parameters beginning with replace-, and replace the relevant placeholder
    const replaceValue = urlParams.get('replace-ip');
    // console.log(textToReplace, replaceValue); 
    // If the 'replace-ip' parameter exists in the URL, replace the text
    // FIXME: if it doesn't exist, replace with a default, or optionally with one from the frontmatter
    if (replaceValue) { 
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

