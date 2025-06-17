function calendar_sync(baseurl) {
  const xhr = new XMLHttpRequest();
  xhr.open("GET", baseurl+"/sync", false);
  xhr.onload = function() {
    if(xhr.status !== 200) {
      console.log("problem with sync endpoint: ", xhr.status);
      return
    }
    console.log("all synced up");
  };
  xhr.onerror = function() {
    console.log("uh oh, failed to sync");
  };
  xhr.send();
}

function calendar_refresh() {
  ec.refetchEvents();
}
