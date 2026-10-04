import {cp, mkdir} from 'node:fs/promises';
await mkdir('vendor/leaflet', {recursive: true});
await cp('node_modules/leaflet/dist', 'vendor/leaflet', {recursive: true});
