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
    const parameterNames = new Set();
    const variableNames = new Set();
    const attributeNames = new Set();
    
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
            const previousElement = span.previousElementSibling;
            
            // Find next non-whitespace element
            let nextNonWhitespace = nextElement;
            while (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '') {
                nextNonWhitespace = nextNonWhitespace.nextElementSibling;
            }
            
            // Find previous non-whitespace element
            let previousNonWhitespace = previousElement;
            while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                previousNonWhitespace = previousNonWhitespace.previousElementSibling;
            }
            
            if (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '=') {
                // Check if it's a named argument in a function call
                if (previousNonWhitespace && (previousNonWhitespace.textContent.trim() === '(' || previousNonWhitespace.textContent.trim() === ',')) {
                    // This is a named parameter
                    span.setAttribute('data-parameter', 'true');
                    parameterNames.add(span.textContent.trim());
                }
                // Else, it's an assignment, don't mark as parameter
            }
            else {
                // This is likely a method call
                methodNames.add(span.textContent.trim());
                span.setAttribute('data-function', 'true');
                functionNames.add(span.textContent.trim());
            }
        }
    });

    // Functions (definitions)
    const functions = document.querySelectorAll('.doc-signature .nf, .md-code__content .nf');
    functions.forEach(span => {
        if (!span.closest('.sd')) {
            span.setAttribute('data-function', 'true');
            functionNames.add(span.textContent.trim());
        } 
    });

    // Parameters in function signatures (only those with type annotations) - FIXED
    const sigParams = document.querySelectorAll('.doc-signature .n, .md-code__content .n');
    sigParams.forEach(span => {
        if (!span.closest('.sd')) {
            const nextElement = span.nextElementSibling;
            const previousElement = span.previousElementSibling;
            
            // Check if this span is after '->' (return type, not parameter)
            let isAfterArrow = false;
            let checkElement = span.previousElementSibling;
            while (checkElement) {
                if (checkElement.textContent.trim() === '->') {
                    isAfterArrow = true;
                    break;
                }
                checkElement = checkElement.previousElementSibling;
            }

            if (!isAfterArrow) {
                // Find next and previous non-whitespace elements
                let nextNonWhitespace = nextElement;
                while (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '') {
                    nextNonWhitespace = nextNonWhitespace.nextElementSibling;
                }
                
                let previousNonWhitespace = previousElement;
                while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                    previousNonWhitespace = previousNonWhitespace.previousElementSibling;
                }

                if (span.closest('.doc-signature')) {
                    // In doc-signatures, mark both type annotations and default values as parameters
                    if ((nextNonWhitespace && nextNonWhitespace.textContent.trim() === ':') ||
                        (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '=')) {
                        span.setAttribute('data-parameter', 'true');
                        parameterNames.add(span.textContent.trim());
                    }
                } else if (span.closest('.md-code__content')) {
                    // In code blocks, only mark type annotations as parameters if in function context
                    // Check if we're in a function definition (look for nearby .nf)
                    let isInFunctionDef = false;
                    let contextCheck = span.parentElement;
                    while (contextCheck && contextCheck !== document) {
                        if (contextCheck.querySelector && contextCheck.querySelector('.nf')) {
                            isInFunctionDef = true;
                            break;
                        }
                        contextCheck = contextCheck.parentElement;
                    }
                    
                    // Also check if we're between parentheses (parameter list)
                    let inParamList = false;
                    let parenCheck = span;
                    while (parenCheck.previousElementSibling) {
                        parenCheck = parenCheck.previousElementSibling;
                        if (parenCheck.textContent.trim() === '(') {
                            inParamList = true;
                            break;
                        }
                    }
                    
                    if (nextNonWhitespace && nextNonWhitespace.textContent.trim() === ':' && 
                        (isInFunctionDef || inParamList)) {
                        span.setAttribute('data-parameter', 'true');
                        parameterNames.add(span.textContent.trim());
                    }
                }
            }
        }
    });
    
    // Return types after -> - ENHANCED FOR COMPLEX GENERIC TYPES
    const arrows = document.querySelectorAll('.doc-signature .o, .md-code__content .o');
    arrows.forEach(span => {
        if (span.textContent.trim() === '->') {
            let nextElement = span.nextElementSibling;
            let inReturnType = true;
            let typeDepth = 0;
            
            while (nextElement && inReturnType) {
                const nextText = nextElement.textContent.trim();
                const nextClasses = nextElement.classList;
                
                // Skip whitespace and punctuation
                if (nextClasses.contains('w') || nextClasses.contains('p') || nextText === '') {
                    nextElement = nextElement.nextElementSibling;
                    continue;
                }
                
                // Stop conditions - end of return type
                if (nextText === ':' || nextText === ')' || nextText === ',' ||  // Parameter boundaries
                    nextClasses.contains('k') || nextClasses.contains('nf') || nextClasses.contains('nc') ||  // Keywords, function/class defs
                    typeDepth < 0) {
                    break;
                }
                
                // Track bracket depth for nested generic types
                if (nextText === '[' || nextText === '(' || nextText === '{') {
                    typeDepth++;
                }
                if (nextText === ']' || nextText === ')' || nextText === '}') {
                    typeDepth = Math.max(0, typeDepth - 1);
                }
                
                // Tag type elements and handle generic parameters
                if (nextClasses.contains('n') || nextClasses.contains('nb') || nextClasses.contains('nc')) {
                    // Add return type tag if not already tagged
                    if (!nextElement.hasAttribute('data-return-type')) {
                        nextElement.setAttribute('data-return-type', 'true');
                    }
                    
                    // Also check if this is a generic parameter (inside brackets)
                    let isGenericParam = false;
                    let genericCheck = nextElement;
                    
                    // Look forward for closing bracket
                    while (genericCheck.nextElementSibling) {
                        genericCheck = genericCheck.nextElementSibling;
                        const genericText = genericCheck.textContent.trim();
                        
                        if (genericText === ']' || genericText === ')') {
                            isGenericParam = true;
                            break;
                        }
                        
                        // If we hit a comma outside brackets, it's a generic parameter
                        if (genericText === ',' && typeDepth === 0) {
                            isGenericParam = true;
                            break;
                        }
                    }
                    
                    if (isGenericParam && !nextElement.hasAttribute('data-type-annotation')) {
                        nextElement.setAttribute('data-type-annotation', 'true');
                    }
                }
                
                nextElement = nextElement.nextElementSibling;
            }
        }
    });

    // Collect variable names from assignments in code blocks
    const assignments = document.querySelectorAll('.md-code__content .n');
    assignments.forEach(span => {
        if (!span.closest('.sd')) {
            const nextElement = span.nextElementSibling;
            const previousElement = span.previousElementSibling;
            
            let nextNonWhitespace = nextElement;
            while (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '') {
                nextNonWhitespace = nextNonWhitespace.nextElementSibling;
            }
            
            let previousNonWhitespace = previousElement;
            while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                previousNonWhitespace = previousNonWhitespace.previousElementSibling;
            }
            
            if (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '=' && 
                !(previousNonWhitespace && previousNonWhitespace.textContent.trim() === '.')) {
                variableNames.add(span.textContent.trim());
            }
        }
    });

    // Collect attribute names from attribute access patterns in code blocks
    const attributes = document.querySelectorAll('.md-code__content .n');
    attributes.forEach(span => {
        if (!span.closest('.sd')) {
            const previousElement = span.previousElementSibling;
            const nextElement = span.nextElementSibling;
            
            let previousNonWhitespace = previousElement;
            while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                previousNonWhitespace = previousNonWhitespace.previousElementSibling;
            }
            
            if (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '.' && 
                !(nextElement && nextElement.textContent.trim() === '(')) {
                // Don't add function/method names as attributes
                if (!functionNames.has(span.textContent.trim()) && !methodNames.has(span.textContent.trim())) {
                    attributeNames.add(span.textContent.trim());
                }
            }
        }
    });

    // ULTRA-MINIMAL: Just detect typing classes in imports
    const typingSpans = document.querySelectorAll('.md-code__content .n');
    typingSpans.forEach(span => {
        if (!span.closest('.sd')) {
            const text = span.textContent.trim();
            
            // Only target known typing classes
            const typingClasses = ['List', 'Dict', 'Any', 'Optional', 'Union', 'Tuple', 'Set', 'Callable', 'Type', 'Literal', 'Annotated'];
            if (typingClasses.includes(text)) {
                
                // Check if this is in an import from typing module
                let prev = span;
                let foundTyping = false;
                let foundImport = false;
                
                // Look back for "from typing import"
                for (let i = 0; i < 8 && prev.previousElementSibling; i++) {
                    prev = prev.previousElementSibling;
                    
                    if (prev.classList.contains('nn') && prev.textContent.trim() === 'typing') {
                        foundTyping = true;
                    }
                    if (prev.classList.contains('kn') && prev.textContent.trim() === 'from') {
                        foundImport = true;
                    }
                    if (foundTyping && foundImport) {
                        break;
                    }
                }
                
                // If we found the typing import pattern, tag it as class
                if (foundTyping && foundImport) {
                    // Only add if not already tagged
                    if (!span.hasAttribute('data-class')) {
                        classNames.add(text);
                        span.setAttribute('data-class', 'true');
                    }
                }
            }
        }
    });

    // Collect imported functions and classes from import statements
    const importStatements = document.querySelectorAll('.doc-signature .n, .md-code__content .n');
    importStatements.forEach(span => {
        if (!span.closest('.sd')) {
            const text = span.textContent.trim();
            const previousElement = span.previousElementSibling;
            const nextElement = span.nextElementSibling;
            
            // Find previous non-whitespace element (should be 'import' keyword)
            let previousNonWhitespace = previousElement;
            while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                previousNonWhitespace = previousNonWhitespace.previousElementSibling;
            }
            
            // Find next non-whitespace element (should be comma or closing parenthesis)
            let nextNonWhitespace = nextElement;
            while (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '') {
                nextNonWhitespace = nextNonWhitespace.nextElementSibling;
            }
            
            // Check if this is part of an import statement
            if (previousNonWhitespace && 
                (previousNonWhitespace.classList.contains('kn') ||  // from/import keyword
                 previousNonWhitespace.textContent.trim() === 'from' || 
                 previousNonWhitespace.textContent.trim() === 'import') &&
                (nextNonWhitespace === null || 
                 nextNonWhitespace.textContent.trim() === ',' || 
                 nextNonWhitespace.textContent.trim() === ')' )) {
                
                // FIXED: More reliable module detection
                let moduleContext = '';
                let moduleCheck = span;
                while (moduleCheck.previousElementSibling) {
                    moduleCheck = moduleCheck.previousElementSibling;
                    if (moduleCheck.classList.contains('nn')) {
                        moduleContext = moduleCheck.textContent.trim();
                        break;
                    }
                    // Stop if we go too far
                    if (moduleCheck.classList.contains('kn') || moduleCheck.textContent.trim() === 'from') {
                        break;
                    }
                }
                
                // Function imports - keep existing logic unchanged
                if (text.match(/^[a-z_][a-z0-9_]*$/) && !text.match(/^(List|Dict|Any|Optional|Union|Tuple|Set|Dict|Callable|Type|Literal)$/)) {
                    // Check if it's from a known module that contains functions
                    if (moduleContext === 'klaw_types' || 
                        moduleContext.match(/^[a-z_][a-z0-9_]*$/) ||  // Python module
                        !moduleContext.match(/^(typing|collections)$/)) {  // Not from typing/collections
                    
                        // Additional check: if it's not a built-in type or known class name pattern
                        if (!classNames.has(text) && !text.match(/^[A-Z][a-zA-Z0-9]*$/)) {
                            functionNames.add(text);
                            span.setAttribute('data-function', 'true');
                        }
                    }
                }
                
                // FIXED: Class imports - simplified detection (UNIFIED FOR ALL MODULES)
                if (text.match(/^[A-Z][a-zA-Z0-9]*$/) || 
                    ['List', 'Dict', 'Any', 'Optional', 'Union', 'Tuple', 'Set', 'Callable', 'Type', 'Literal', 'Annotated'].includes(text)) {
                    
                    // Simplified: tag as class if we found ANY module context (klaw_types, typing, etc.)
                    if (moduleContext && moduleContext.length > 0) {
                        classNames.add(text);
                        span.setAttribute('data-class', 'true');
                    }
                }
            }
        }
    });


    const typeAnnotations = document.querySelectorAll('.doc-signature .n, .md-code__content .n, .doc-signature .nb, .md-code__content .nb');
    typeAnnotations.forEach(span => {
        if (!span.closest('.sd')) {
            const text = span.textContent.trim();
            const previousElement = span.previousElementSibling;
            const nextElement = span.nextElementSibling;
            
            // Find previous non-whitespace element (should be colon for type annotation)
            let previousNonWhitespace = previousElement;
            while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                previousNonWhitespace = previousNonWhitespace.previousElementSibling;
            }
            
            // Find next non-whitespace element (to ensure we're in a type position)
            let nextNonWhitespace = nextElement;
            while (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '') {
                nextNonWhitespace = nextNonWhitespace.nextElementSibling;
            }
            
            // Check if this is a type annotation (after colon, not a return type)
            if (previousNonWhitespace && previousNonWhitespace.textContent.trim() === ':' &&
                !span.hasAttribute('data-return-type') &&  // Not already a return type
                !span.closest('.md-code__content .sd')
            ) {  
                
                // Ensure we're in a function signature context (look for nearby function definition)
                let functionContext = false;
                let contextCheck = span.parentElement;
                let contextDistance = 0;
                const maxContextDistance = 20;
                
                while (contextCheck && contextCheck !== document && contextDistance < maxContextDistance) {
                    if (contextCheck.querySelector('.nf') ||  // Function name
                        (contextCheck.classList.contains('k') && contextCheck.textContent.trim() === 'def')) {
                        functionContext = true;
                        break;
                    }
                    contextCheck = contextCheck.parentElement;
                    contextDistance++;
                }
                
                if (functionContext) {
                    // Tag the type elements (.n, .nb, .nc classes)
                    if (span.classList.contains('n') || 
                        span.classList.contains('nb') || 
                        span.classList.contains('nc')) {
                        
                        // Add type annotation tag (don't override existing class tags)
                        if (!span.hasAttribute('data-type-annotation')) {
                            span.setAttribute('data-type-annotation', 'true');
                        }
                    }
                    
                    // Also tag nested types in brackets (like Dict[str, Any])
                    if (span.textContent.includes('[') || span.textContent.includes('(') || span.textContent.includes('{')) {
                        let nestedCheck = span.nextElementSibling;
                        while (nestedCheck && nestedCheck !== document) {
                            const nestedText = nestedCheck.textContent.trim();
                            
                            // Stop at closing brackets or parameter boundaries
                            if (nestedText === ']' || nestedText === ')' || nestedText === '}' || 
                                nestedText === ',' || nestedText === ':' || nestedText === '->') {
                                break;
                            }
                            
                            // Tag nested type elements
                            if ((nestedCheck.classList.contains('n') || 
                                 nestedCheck.classList.contains('nb') || 
                                 nestedCheck.classList.contains('nc')) &&
                                !nestedCheck.hasAttribute('data-type-annotation')) {
                                nestedCheck.setAttribute('data-type-annotation', 'true');
                            }
                            
                            nestedCheck = nestedCheck.nextElementSibling;
                        }
                    }
                }
            }
        }
    });

    // References (from .n) - distinguish between functions, classes, and variables - FIXED
    const names = document.querySelectorAll('.doc-signature .n, .md-code__content .n');
    names.forEach(span => {
        if (!span.closest('.sd')) {
            const text = span.textContent.trim();
            const nextElement = span.nextElementSibling;
            previousElement = span.previousElementSibling;

            // Find next non-whitespace element
            let nextNonWhitespace = nextElement;
            while (nextNonWhitespace && nextNonWhitespace.textContent.trim() === '') {
                nextNonWhitespace = nextNonWhitespace.nextElementSibling;
            }
            
            // Find previous non-whitespace element
            let previousNonWhitespace = previousElement;
            while (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '') {
                previousNonWhitespace = previousNonWhitespace.previousElementSibling;
            }

            // Skip parameters, type annotations, assignments, and function calls
            if (nextNonWhitespace && (nextNonWhitespace.textContent.trim() === ',' || 
                               (nextNonWhitespace.textContent.trim() === '=' && !(previousNonWhitespace && previousNonWhitespace.textContent.trim() === '.')) ||
                               (nextNonWhitespace.textContent.trim() === ':' && !(previousNonWhitespace && previousNonWhitespace.textContent.trim() === '.')))) {
                return;
            }            

            // Special case for function calls
            if (
                (
                    nextNonWhitespace && nextNonWhitespace.textContent.trim() === '(' &&
                    text.match(/^[a-z_][a-z0-9_]*$/)
                ) ||
                nextNonWhitespace && (
                    nextNonWhitespace.textContent.trim() === '([' &&
                    text.match(/^[a-z_][a-z0-9_]*$/)
                )||
                nextNonWhitespace && nextNonWhitespace.textContent.trim() === '({' ||
                (
                    nextNonWhitespace && nextNonWhitespace.textContent.trim() === '()' &&
                    text.match(/^[a-z_][a-z0-9_]*$/)
                )||
                nextNonWhitespace && nextNonWhitespace.textContent.trim() === '())' ||
                nextNonWhitespace && nextNonWhitespace.textContent.trim() === '()]'
    
            ) {
                span.setAttribute('data-function', 'true');
                return;
            }

            // Check what type of reference this is - PRIORITIZE VARIABLES OVER PARAMETERS
            let dataType = '';

            // First, check for attribute access
            if (previousNonWhitespace && previousNonWhitespace.textContent.trim() === '.' && attributeNames.has(text)) {
                dataType = 'attribute';
            }
            // Then check if this is likely a variable reference (not in parameter position)
            else if (
                variableNames.has(text) &&
                !(parameterNames.has(text) || span.hasAttribute('data-type-annotation'))
            ) {
                // Only override if not clearly a parameter (e.g., after comma in function call)
                const isClearlyParameter = previousNonWhitespace && previousNonWhitespace.textContent.trim() === ',';
                if (!isClearlyParameter) {
                    dataType = 'variable';
                }
            }
            // Then check for actual parameters (only if not tagged as variable)
            else if (parameterNames.has(text) && dataType !== 'variable') {
                dataType = 'parameter';
            }
            else if ((functionNames.has(text) || methodNames.has(text)) &&
                     !(classMethods.has(text) || classNames.has(text))) {
                dataType = 'function';
            }
            else if (classNames.has(text) && !(
                span.hasAttribute('data-type-annotation') ||
                span.hasAttribute('data-return-type')
            )) {
                dataType = 'class';
            }

            if (dataType) {
                // Remove conflicting attributes before setting new one - ENHANCED
                if (dataType === 'attribute' || dataType === 'variable') {
                    span.removeAttribute('data-parameter');
                    span.removeAttribute('data-function');  // Also remove if it was mis-tagged
                }
                if (dataType === 'parameter') {
                    span.removeAttribute('data-variable');
                    span.removeAttribute('data-attribute');
                }
                if (dataType === 'function') {
                    span.removeAttribute('data-variable');
                    span.removeAttribute('data-parameter');
                }
                if (dataType === 'class') {
                    span.removeAttribute('data-variable');
                    span.removeAttribute('data-parameter');
                    span.removeAttribute('data-function');
                }
                
                // Set the new attribute
                span.setAttribute('data-' + dataType, 'true');
            }
        }
    });
    
});
