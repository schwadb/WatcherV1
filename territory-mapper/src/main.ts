import './style.css';
import { registerSW } from 'virtual:pwa-register';
import { App, blankProject } from './app';
import { loadBoundaries } from './boundaries';
import { createMap } from './map';
import { listProjects, loadProject, saveProject } from './storage';

registerSW({ immediate: true });

async function boot(): Promise<void> {
  const boundaries = await loadBoundaries();

  // resolve project: last-used, else most recent, else new
  let project = null;
  const lastId = localStorage.getItem('tm-last-project');
  if (lastId) project = (await loadProject(lastId)) ?? null;
  if (!project) {
    const all = await listProjects();
    project = all.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0] ?? null;
  }
  if (!project) {
    project = blankProject();
    await saveProject(project);
  }
  localStorage.setItem('tm-last-project', project.id);

  const tm = await createMap(document.getElementById('map')!, boundaries);
  if (project.mapView) {
    tm.map.jumpTo({ center: project.mapView.center, zoom: project.mapView.zoom });
  }

  const app = new App();
  await app.init(project, boundaries, tm);
}

boot().catch((err) => {
  console.error('boot failed', err);
  const t = document.getElementById('toast');
  if (t) {
    t.textContent = `Failed to start: ${err?.message ?? err}. If you are offline, connect once to load the base map.`;
    t.hidden = false;
  }
});
