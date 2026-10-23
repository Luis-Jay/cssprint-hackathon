declare module '@tanstack/react-router';
declare module 'lucide-react';
declare module '@radix-ui/react-slot';
declare module '@radix-ui/react-progress';

// CSS imports with ?url (Vite/Next style) or CSS modules
declare module "*.css?url" {
	const href: string;
	export default href;
}

declare module "*.svg?url" {
	const href: string;
	export default href;
}

declare module "*.module.css" {
	const classes: { [key: string]: string };
	export default classes;
}

// Provide common relative import declarations used in this repo
declare module "./styles.css?url" {
	const href: string;
	export default href;
}

declare module "../styles.css?url" {
	const href: string;
	export default href;
}

