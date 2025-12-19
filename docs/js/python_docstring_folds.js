/**
 * Python Docstring Folding for MkDocs - Multi-Level Indentation Support
 * Handles docstrings at any multiple of 4 spaces (4, 8, 12, etc.)
 * Folds class and function docstrings uniformly
 * Relaxed validation to allow code examples in docstrings
 * Starts COLLAPSED by default
 */

(() => {
	console.log("Docstring folding script initializing...");

	function initializeFolding() {
		console.log("Initializing docstring folding...");

		const codeBlocks = document.querySelectorAll(
			".md-content .md-code__content",
		);
		console.log(`Found ${codeBlocks.length} code blocks to process`);

		let totalFolds = 0;
		let singleLinesSkipped = 0;

		codeBlocks.forEach((codeBlock, blockIndex) => {
			console.log(`Processing code block ${blockIndex + 1}`);

			const lineSpans = Array.from(
				codeBlock.querySelectorAll('[id^="__span-0-"]'),
			);
			console.log(`  Found ${lineSpans.length} line spans`);

			if (lineSpans.length === 0) return;

			let i = 0;
			while (i < lineSpans.length) {
				const currentLine = lineSpans[i];
				const lineText = currentLine.textContent;
				const trimmedText = lineText.trim();

				// Look for docstring opening: any multiple of 4 spaces + """
				const openingRegex = /^(\s*)"""/;
				const openingMatch = lineText.match(openingRegex);

				if (openingMatch) {
					const indentSpaces = openingMatch[1].length;
					console.log(
						`  Found potential docstring opening at line ${i + 1}: indent=${indentSpaces}, "${trimmedText.substring(0, 30)}..."`,
					);

					// Check if single-line (closing """ on same line)
					if (trimmedText.includes('"""', 4)) {
						// Has closing after opening
						console.log(`  Single-line docstring at line ${i + 1} - skipping`);
						singleLinesSkipped++;
						i++;
						continue;
					}

					// Find the end: next line with same indent + """
					let endIndex = -1;

					for (let j = i + 1; j < lineSpans.length; j++) {
						const testLine = lineSpans[j];
						const testText = testLine.textContent;
						const testTrimmed = testText.trim();

						// Check if this line starts with same indent + """
						const testMatch = testText.match(openingRegex);
						if (testMatch && testMatch[1].length === indentSpaces) {
							endIndex = j;
							console.log(
								`  Found docstring closing at line ${j + 1} (indent ${indentSpaces})`,
							);
							break;
						}
					}

					if (endIndex !== -1 && endIndex > i) {
						const candidateLines = lineSpans.slice(i, endIndex + 1);
						const numContentLines = candidateLines.length - 2; // Exclude opening/closing

						// RELAXED validation: only check reasonable length (docstrings can contain code examples)
						const hasReasonableLength =
							numContentLines > 0 && numContentLines < 100;

						if (hasReasonableLength) {
							console.log(
								`  Valid docstring: lines ${i + 1}-${endIndex + 1} (${candidateLines.length} lines, ${numContentLines} content)`,
							);
							createDocstringFold(codeBlock, candidateLines, i);
							totalFolds++;
							i = endIndex + 1;
						} else {
							console.log(
								`  Invalid length - skipping (${numContentLines} content lines)`,
							);
							i++;
						}
					} else {
						console.log(
							`  No matching closing found for opening at line ${i + 1}`,
						);
						i++;
					}
				} else {
					i++;
				}
			}
		});

		console.log(
			`Created ${totalFolds} docstring folds, skipped ${singleLinesSkipped} single-lines`,
		);
	}

	function createDocstringFold(codeBlock, docstringLines, startIndex) {
		const foldContainer = document.createElement("div");
		foldContainer.className = "docstring-fold docstring-collapsed"; // Start COLLAPSED

		// Preview: First line (opening), always visible
		const previewLine = docstringLines[0].cloneNode(true);
		previewLine.classList.add("docstring-preview");
		const originalId = previewLine.id;
		previewLine.id = `docstring-preview-${startIndex}`;

		// Add toggle indicator to line number
		const lineno = previewLine.querySelector(".linenos");
		if (lineno) {
			lineno.classList.add("fold-indicator");
			lineno.style.cursor = "pointer";
			lineno.style.userSelect = "none";
			lineno.title = "Click to toggle docstring";

			lineno.addEventListener("click", (e) => {
				e.preventDefault();
				e.stopPropagation();
				toggleFold(foldContainer, lineno);
			});

			lineno.addEventListener("keydown", (e) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					toggleFold(foldContainer, lineno);
				}
			});
		}

		// Content: All lines after first (collapsible, including closing)
		const contentContainer = document.createElement("div");
		contentContainer.className = "docstring-content";
		// Start hidden
		contentContainer.style.maxHeight = "0";
		contentContainer.style.opacity = "0";
		contentContainer.style.overflow = "hidden";

		for (let k = 1; k < docstringLines.length; k++) {
			const lineClone = docstringLines[k].cloneNode(true);
			lineClone.classList.add("docstring-line");

			// Preserve IDs with docstring suffix
			if (lineClone.id) {
				lineClone.id = lineClone.id.replace(
					/__span-0-\d+$/,
					`docstring-line-${startIndex + k}`,
				);
			}

			contentContainer.appendChild(lineClone);
		}

		foldContainer.appendChild(previewLine);
		foldContainer.appendChild(contentContainer);

		// Replace original lines
		const firstOriginal = docstringLines[0];
		if (firstOriginal && firstOriginal.parentNode) {
			firstOriginal.parentNode.insertBefore(foldContainer, firstOriginal);

			docstringLines.forEach((line) => {
				if (line.parentNode) {
					line.parentNode.removeChild(line);
				}
			});

			// Restore anchor for preview line
			if (originalId) {
				const anchor = document.createElement("a");
				anchor.id = originalId.replace("__span-0-", "__codelineno-0-");
				anchor.name = anchor.id;
				anchor.href = `#${anchor.name}`;
				foldContainer.insertBefore(anchor, previewLine);
			}
		}

		console.log(
			`  Fold inserted for lines ${startIndex + 1}-${startIndex + docstringLines.length}`,
		);
	}

	function toggleFold(foldContainer, indicator) {
		const isExpanded = foldContainer.classList.contains("docstring-expanded");
		const content = foldContainer.querySelector(".docstring-content");

		if (isExpanded) {
			foldContainer.classList.remove("docstring-expanded");
			foldContainer.classList.add("docstring-collapsed");
			if (indicator)
				indicator.textContent = indicator.textContent.replace(" ", " ");
			content.style.maxHeight = "0";
			content.style.opacity = "0";
			content.style.overflow = "hidden";
		} else {
			foldContainer.classList.remove("docstring-collapsed");
			foldContainer.classList.add("docstring-expanded");
			if (indicator)
				indicator.textContent = indicator.textContent.replace(" ", " ");
			content.style.maxHeight = "4000px";
			content.style.opacity = "1";
			content.style.overflow = "visible";
		}
	}

	// Initialize when DOM ready
	function init() {
		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", () =>
				setTimeout(initializeFolding, 100),
			);
		} else {
			setTimeout(initializeFolding, 100);
		}
	}

	// Watch for dynamic content changes
	const observer = new MutationObserver(() =>
		setTimeout(initializeFolding, 200),
	);
	observer.observe(document.body, { childList: true, subtree: true });

	init();
	window.DocstringFolding = { initialize: initializeFolding };
	console.log("Multi-level indentation docstring folding initialized");
})();
