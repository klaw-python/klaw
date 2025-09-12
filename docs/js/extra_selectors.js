document.addEventListener('DOMContentLoaded', function() {
    // Keywords
    const keywords = document.querySelectorAll('.doc-signature .k, .md-code__content .k');
    keywords.forEach(span => {
        const text = span.textContent.trim();
        if (text === 'def' || text === 'class') {
            span.setAttribute('data-keyword', text);
        }
    });

    // Collect function, method, classmethod, and class names from definitions (excluding docstrings)
    const functionNames = new Set();
    const methodNames = new Set();
    const classMethods = new Set();
    const classNames = new Set();
    
    // Functions
    const funcDefs = document.querySelectorAll('.doc-signature .nf, .md-code__content .nf');
    funcDefs.forEach(span => {
        if (!span.closest('.sd')) {
            functionNames.add(span.textContent.trim());
        }
    });
    
    // Classes
    const classDefs = document.querySelectorAll('.doc-signature .nc, .md-code__content .nc');
    classDefs.forEach(span => {
        if (!span.closest('.sd')) {
            classNames.add(span.textContent.trim());
        }
    });
    
    // Collect @classmethod methods
    const decorators = document.querySelectorAll('.doc-signature .nd, .md-code__content .nd');
    decorators.forEach(span => {
        if (span.textContent.trim() === '@classmethod') {
            // Find the next .nf after this decorator
            let nextElement = span.nextElementSibling;
            while (nextElement) {
                if (nextElement.classList && nextElement.classList.contains('nf')) {
                    classMethods.add(nextElement.textContent.trim());
                    break;
                }
                nextElement = nextElement.nextElementSibling;
            }
        }
    });
    
    // Methods and named parameters (from .na)
    const attrNames = document.querySelectorAll('.doc-signature .na, .md-code__content .na');
    attrNames.forEach(span => {
        if (!span.closest('.sd')) {
            const nextElement = span.nextElementSibling;
            if (nextElement && nextElement.textContent.trim() === '=') {
                // This is a named parameter
                span.setAttribute('data-parameter', 'true');
            } else {
                // This is likely a method call
                methodNames.add(span.textContent.trim());
                span.setAttribute('data-function', 'true');
            }
        }
    });

    // Functions (definitions)
    const functions = document.querySelectorAll('.doc-signature .nf, .md-code__content .nf');
    functions.forEach(span => {
        if (!span.closest('.sd')) {
            span.setAttribute('data-function', 'true');
        }
    });

    // Parameters in function signatures (only those with type annotations)
    const sigParams = document.querySelectorAll('.doc-signature .n, .md-code__content .n');
    sigParams.forEach(span => {
        if (!span.closest('.sd')) {
            const nextElement = span.nextElementSibling;
            if (nextElement && nextElement.textContent.trim() === ':') {
                span.setAttribute('data-parameter', 'true');
            }
        }
    });

    // Return types after ->
    const arrows = document.querySelectorAll('.doc-signature .o, .md-code__content .o');
    arrows.forEach(span => {
        if (span.textContent.trim() === '->') {
            let nextElement = span.nextElementSibling;
            while (nextElement) {
                if (nextElement.classList && (nextElement.classList.contains('n') || nextElement.classList.contains('nb'))) {
                    nextElement.setAttribute('data-return-type', 'true');
                } else if (nextElement.classList && !nextElement.classList.contains('w')) {
                    // Stop at non-whitespace, non-type spans
                    break;
                }
                nextElement = nextElement.nextElementSibling;
            }
        }
    });

    // References (from .n) - distinguish between functions, classes, and variables
    const names = document.querySelectorAll('.doc-signature .n, .md-code__content .n');
    names.forEach(span => {
        if (!span.closest('.sd')) {
            const text = span.textContent.trim();
            const nextElement = span.nextElementSibling;
            
            // Skip parameters, type annotations, assignments, and function calls
            if (nextElement && (nextElement.textContent.trim() === '=' || 
                               nextElement.textContent.trim() === ':' ||
                               nextElement.textContent.trim() === ',' ||
                               nextElement.textContent.trim() === ')')) {
                return;
            }
            
            // Check what type of reference this is
            if (functionNames.has(text) || methodNames.has(text) || classMethods.has(text)) {
                span.setAttribute('data-function', 'true');
            } else if (classNames.has(text)) {
                span.setAttribute('data-class', 'true');
            }
            // Variables and other identifiers are left unhighlighted
        }
    });
    
});