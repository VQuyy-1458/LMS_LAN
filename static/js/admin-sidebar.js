/* Use the same reference icons on every sidebar, including legacy content pages. */
(() => {
  const sidebar=document.querySelector('.admin-sidebar-unified .main-sidebar');
  if(sidebar)window.classroomAdminIcons.decorate(sidebar);
})();
