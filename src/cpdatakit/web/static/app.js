const projectForm = document.querySelector('form[action="/api/projects"]');

if (projectForm) {
  projectForm.dataset.localOnly = "true";
}
