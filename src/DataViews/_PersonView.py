#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

# $Id$

#------------------------------------------------------------------------
#
# standard python modules
#
#------------------------------------------------------------------------

from gettext import gettext as _
import cPickle as pickle

try:
    set()
except:
    from sets import Set as set

#-------------------------------------------------------------------------
#
# gtk
#
#-------------------------------------------------------------------------
import gtk
import pango
from gtk.gdk import ACTION_COPY, BUTTON1_MASK

#-------------------------------------------------------------------------
#
# GRAMPS modules
#
#-------------------------------------------------------------------------
import RelLib
from DisplayModels import PeopleModel
import PageView
import NameDisplay
import Utils
import QuestionDialog
import TreeTips
import Errors
import Config
import const

from Editors import EditPerson
from Filters import SearchBar, PersonSidebarFilter
from DdTargets import DdTargets

column_names = [
    _('Name'),
    _('ID') ,
    _('Gender'),
    _('Birth Date'),
    _('Birth Place'),
    _('Death Date'),
    _('Death Place'),
    _('Spouse'),
    _('Last Change'),
    _('Cause of Death'),
    ]


        
class PersonView(PageView.PersonNavView):

    def __init__(self,dbstate,uistate):
        PageView.PersonNavView.__init__(self, _('People'), dbstate, uistate)
        
        self.inactive = False
        dbstate.connect('database-changed',self.change_db)
        dbstate.connect('active-changed',self.goto_active_person)
        self.handle_col = PeopleModel.COLUMN_INT_ID
        self.model = None
        self.generic_filter = None

        self.func_list = {
            'F2' : self.key_goto_home_person,
            'F3' : self.key_edit_selected_person,
            }
        self.dirty = True

        Config.client.notify_add("/apps/gramps/interface/filter",
                                 self.filter_toggle)
        
    def change_page(self):
        pass
        
    def define_actions(self):
        """
        Required define_actions function for PageView. Builds the action
        group information required. We extend beyond the normal here,
        since we want to have more than one action group for the PersonView.
        Most PageViews really won't care about this.

        Special action groups for Forward and Back are created to allow the
        handling of navigation buttons. Forward and Back allow the user to
        advance or retreat throughout the history, and we want to have these
        be able to toggle these when you are at the end of the history or
        at the beginning of the history.
        """

        PageView.PersonNavView.define_actions(self)
        
        self.add_action('Add', gtk.STOCK_ADD, _("_Add"),
                        tip=_("Add a new person"), callback=self.add)
        self.add_action('Edit', gtk.STOCK_EDIT, _("_Edit"),
                        tip=_("Edit the selected person"), callback=self.edit)
        self.add_action('Remove', gtk.STOCK_REMOVE, _("_Remove"),
                        tip=_("Remove the selected person"),
                        callback=self.remove)
        self.add_action('OpenAllNodes', None, _("Expand all nodes"),
                        callback=self.open_all_nodes)
        self.add_action('CloseAllNodes', None, _("Collapse all nodes"),
                        callback=self.close_all_nodes)
        self.add_action('Jump', None, _("_Jump"),
                        accel="<control>j",callback=self.jumpto)

        self.add_action('ColumnEdit', gtk.STOCK_PROPERTIES,
                        _('_Column Editor'), callback=self.column_editor,)

        self.add_action('CmpMerge', None, _('_Compare and merge'),
                        callback=self.cmp_merge) 
        self.add_action('FastMerge', None, _('_Fast merge'),
                        callback=self.fast_merge)

    def cmp_merge(self, obj):
        mlist = self.get_selected_objects()

        if len(mlist) != 2:
            QuestionDialog.ErrorDialog(
		_("Cannot merge people"),
		_("Exactly two people must be selected to perform a merge. "
		  "A second person can be selected by holding down the "
		  "control key while clicking on the desired person."))
        else:
            import Merge 
            p1 = self.db.get_person_from_handle(mlist[0])
            p2 = self.db.get_person_from_handle(mlist[1])
            if p1 and p2:
                Merge.PersonCompare(self.dbstate, self.uistate, p1, p2)
            else:
                QuestionDialog.ErrorDialog(
                    _("Cannot merge people"),
                    _("Exactly two people must be selected to perform a "
                      "merge. A second person can be selected by holding "
                      "down the control key while clicking on the desired "
                      "person."))

    def fast_merge(self, obj):
        mlist = self.get_selected_objects()

        if len(mlist) != 2:
            QuestionDialog.ErrorDialog(
		_("Cannot merge people"),
		_("Exactly two people must be selected to perform a merge. "
		  "A second person can be selected by holding down the "
		  "control key while clicking on the desired person."))
        else:
            import Merge
            
            p1 = self.db.get_person_from_handle(mlist[0])
            p2 = self.db.get_person_from_handle(mlist[1])
            if p1 and p2:
                Merge.MergePeopleUI(self.dbstate, self.uistate, p1, p2)
            else:
                QuestionDialog.ErrorDialog(
		    _("Cannot merge people"),
		    _("Exactly two people must be selected to perform a merge. "
		      "A second person can be selected by holding down the "
		      "control key while clicking on the desired person."))
                
    def column_editor(self,obj):
        import ColumnOrder

        ColumnOrder.ColumnOrder(
            _('Select Person Columns'),
            self.uistate,
            self.dbstate.db.get_person_column_order(),
            column_names,
            self.set_column_order)

    def set_column_order(self, column_list):
        self.dbstate.db.set_person_column_order(column_list)
        self.build_columns()
        self.setup_filter()

    def get_stock(self):
        """
        Returns the name of the stock icon to use for the display.
        This assumes that this icon has already been registered with
        GNOME as a stock icon.
        """
        return 'gramps-person'

    def build_widget(self):
        """
        Builds the interface and returns a gtk.Container type that
        contains the interface. This containter will be inserted into
        a gtk.Notebook page.
        """
        hpaned = gtk.HBox()
        self.vbox = gtk.VBox()
        self.vbox.set_border_width(4)
        self.vbox.set_spacing(4)
        
        self.search_bar = SearchBar(self.dbstate, self.uistate,
                                    self.build_tree, self.goto_active_person)
        filter_box = self.search_bar.build()
        
        self.tree = gtk.TreeView()
        self.tree.set_rules_hint(True)
        self.tree.set_headers_visible(True)
        self.tree.set_fixed_height_mode(True)
        self.tree.connect('key-press-event',self.key_press)

        scrollwindow = gtk.ScrolledWindow()
        scrollwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrollwindow.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        scrollwindow.add(self.tree)
        scrollwindow.show_all()

        self.vbox.pack_start(filter_box,False)
        self.vbox.pack_start(scrollwindow,True)

        self.renderer = gtk.CellRendererText()
        self.renderer.set_property('ellipsize',pango.ELLIPSIZE_END)
        self.inactive = False

        self.columns = []

        self.setup_filter()
        self.build_columns()
        self.tree.connect('button-press-event', self.button_press)
        self.tree.connect('drag_data_get', self.drag_data_get)
        self.tree.connect('drag_begin', self.drag_begin)

        self.selection = self.tree.get_selection()
        self.selection.set_mode(gtk.SELECTION_MULTIPLE)
        self.selection.connect('changed',self.row_changed)

        self.filter_sidebar = PersonSidebarFilter(self.filter_clicked)
        self.filter_pane = self.filter_sidebar.get_widget()

        hpaned.pack_start(self.vbox, True, True)
        hpaned.pack_end(self.filter_pane, False, False)
        self.filter_toggle(None, None, None, None)
        return hpaned

    def post(self):
        if Config.get(Config.FILTER):
            self.search_bar.hide()
            self.filter_pane.show()
        else:
            self.search_bar.show()
            self.filter_pane.hide()
        
    def filter_clicked(self):
        self.generic_filter = self.filter_sidebar.get_filter()
        self.build_tree()
    
    def drag_begin(self, widget, *data):
        widget.drag_source_set_icon_stock(self.get_stock())
        
    def ui_definition(self):
        """
        Specifies the UIManager XML code that defines the menus and buttons
        associated with the interface.
        """
        return '''<ui>
          <accelerator action="Jump"/>
          <menubar name="MenuBar">
            <menu action="BookMenu">
              <placeholder name="AddEditBook">
                <menuitem action="AddBook"/>
                <menuitem action="EditBook"/>
              </placeholder>
            </menu>
            <menu action="GoMenu">
              <placeholder name="CommonGo">
                <menuitem action="Back"/>
                <menuitem action="Forward"/>
                <separator/>
                <menuitem action="HomePerson"/>
                <separator/>
              </placeholder>
            </menu>
            <menu action="EditMenu">
              <placeholder name="CommonEdit">
                <menuitem action="Add"/>
                <menuitem action="Edit"/>
                <menuitem action="Remove"/>
              </placeholder>
              <menuitem action="SetActive"/>
              <menuitem action="ColumnEdit"/>
              <menuitem action="FilterEdit"/>
              <placeholder name="Merge">
                <menuitem action="CmpMerge"/>
                <menuitem action="FastMerge"/>
              </placeholder>
            </menu>
          </menubar>
          <toolbar name="ToolBar">
            <placeholder name="CommonNavigation">
              <toolitem action="Back"/>  
              <toolitem action="Forward"/>  
              <toolitem action="HomePerson"/>
            </placeholder>
            <placeholder name="CommonEdit">
              <toolitem action="Add"/>
              <toolitem action="Edit"/>
              <toolitem action="Remove"/>
            </placeholder>
          </toolbar>
          <popup name="Popup">
            <menuitem action="Back"/>
            <menuitem action="Forward"/>
            <menuitem action="HomePerson"/>
            <separator/>
            <menuitem action="OpenAllNodes"/>
            <menuitem action="CloseAllNodes"/>
            <separator/>
            <menuitem action="Add"/>
            <menuitem action="Edit"/>
            <menuitem action="Remove"/>
          </popup>
        </ui>'''

    def change_db(self,db):
        """
        Callback associated with DbState. Whenenver the database
        changes, this task is called. In this case, we rebuild the
        columns, and connect signals to the connected database. Tere
        is no need to store the database, since we will get the value
        from self.state.db
        """
        self.build_columns()
        self.setup_filter()
        self.db = db
        db.connect('person-add', self.person_added)
        db.connect('person-update', self.person_updated)
        db.connect('person-delete', self.person_removed)
        db.connect('person-rebuild', self.build_tree)
        self.build_tree()
        self.bookmarks.update_bookmarks(db.get_bookmarks())
        if self.active:
            self.bookmarks.redraw()

    def goto_active_person(self,obj=None):
        """
        Callback (and usable function) that selects the active person
        in the display tree.

        We have a bit of a problem due to the nature of how GTK works.
        We have unselect the previous path and select the new path. However,
        these cause a row change, which calls the row_change callback, which
        can end up calling change_active_person, which can call
        goto_active_person, causing a bit of recusion. Confusing, huh?

        Unforunately, we row_change has to be able to call change_active_person,
        because the can occur from the interface in addition to programatically.

        TO handle this, we set the self.inactive variable that we can check
        in row_change to look for this particular condition.
        """

        # if there is no active person, or if we have been marked inactive,
        # simply return

        if not self.dbstate.active or self.inactive:
            return

        # mark inactive to prevent recusion
        self.inactive = True

        self._goto()

        # disable the inactive flag
        self.inactive = False

        # update history
        self.handle_history(self.dbstate.active.handle)

    def _goto(self):

        # select the active person in the person view
        p = self.dbstate.active
        try:
            if self.model and p:
                path = self.model.on_get_path(p.get_handle())
                group_name = p.get_primary_name().get_group_name()
                top_name = self.dbstate.db.get_name_group_mapping(group_name)
                top_path = self.model.on_get_path(top_name)
                self.tree.expand_row(top_path,0)

                current = self.model.on_get_iter(path)
                selected = self.selection.path_is_selected(path)
                if current != p.get_handle() or not selected:
                    self.selection.unselect_all()
                    self.selection.select_path(path)
                    self.tree.scroll_to_cell(path,None,1,0.5,0)
        except KeyError:
            self.selection.unselect_all()
            self.uistate.push_message(self.dbstate,
                                      _("Active person not visible"))
            self.dbstate.active = p
        
    def setup_filter(self):
        """
        Builds the default filters and add them to the filter menu.
        """

        cols = []
        cols.append((_("Name"),0))
        for pair in self.dbstate.db.get_person_column_order():
            if not pair[0]:
                continue
            cols.append((column_names[pair[1]],pair[1]))

        self.search_bar.setup_filter(cols)

    def build_tree(self):
        """
        Creates a new PeopleModel instance. Essentially creates a complete
        rebuild of the data. We need to temporarily store the active person,
        since it can change when rows are unselected when the model is set.
        """
        if self.active:

            if Config.get(Config.FILTER):
                filter_info = (PeopleModel.GENERIC, self.generic_filter)
            else:
                filter_info = (PeopleModel.SEARCH, self.search_bar.get_value())

            self.model = PeopleModel(self.dbstate.db, filter_info)

            active = self.dbstate.active
            self.tree.set_model(self.model)

            if const.use_tips and self.model.tooltip_column != None:
                self.tooltips = TreeTips.TreeTips(self.tree,
                                                  self.model.tooltip_column,
                                                  True)

            self.build_columns()
            self.setup_filter()
            self.dbstate.change_active_person(active)
            self._goto()
            self.dirty = False
        else:
            self.dirty = True

#        if Config.get(Config.FILTER):
#            self.search_bar.hide()
#            self.filter_pane.show()
#        else:
#            self.search_bar.show()
#            self.filter_pane.hide()

    def filter_toggle(self, client, cnxn_id, etnry, data):
        if Config.get(Config.FILTER):
            self.search_bar.hide()
            self.filter_pane.show()
            active = True
        else:
            self.search_bar.show()
            self.filter_pane.hide()
            active = False
        self.build_tree()

    def add(self,obj):
        person = RelLib.Person()
        try:
            EditPerson(self.dbstate, self.uistate, [], person)
        except Errors.WindowActiveError:
            pass

    def edit(self,obj):
        if self.dbstate.active:
            try:
                handle = self.dbstate.active.handle
                person = self.dbstate.db.get_person_from_handle(handle)
                EditPerson(self.dbstate, self.uistate, [], person)
            except Errors.WindowActiveError:
                pass

    def open_all_nodes(self,obj):
        self.tree.expand_all()

    def close_all_nodes(self,obj):
        self.tree.collapse_all()

    def remove(self,obj):
        mlist = self.get_selected_objects()
        if len(mlist) == 0:
            return
        
        for sel in mlist:
            p = self.dbstate.db.get_person_from_handle(sel)
            self.active_person = p
            name = NameDisplay.displayer.display(p) 

            msg = _('Deleting the person will remove the person '
                             'from the database.')
            msg = "%s %s" % (msg,Utils.data_recover_msg)
            QuestionDialog.QuestionDialog(_('Delete %s?') % name,msg,
                                          _('_Delete Person'),
                                          self.delete_person_response)

    def delete_person_response(self):
        #self.disable_interface()
        trans = self.dbstate.db.transaction_begin()
        
        n = NameDisplay.displayer.display(self.active_person)

        if self.dbstate.db.get_default_person() == self.active_person:
            self.dbstate.db.set_default_person_handle(None)

        for family_handle in self.active_person.get_family_handle_list():
            if not family_handle:
                continue
            family = self.dbstate.db.get_family_from_handle(family_handle)
            family_to_remove = False
            if self.active_person.get_handle() == family.get_father_handle():
                if family.get_mother_handle():
                    family.set_father_handle(None)
                else:
                    family_to_remove = True
            else:
                if family.get_father_handle():
                    family.set_mother_handle(None)
                else:
                    family_to_remove = True
            if family_to_remove:
                for child_ref in family.get_child_ref_list():
                    child = self.dbstate.db.get_person_from_handle(child_ref.ref)
                    child.remove_parent_family_handle(family_handle)
                    self.dbstate.db.commit_person(child,trans)
                self.dbstate.db.remove_family(family_handle,trans)
            else:
                self.dbstate.db.commit_family(family,trans)

        for family_handle in self.active_person.get_parent_family_handle_list():
            if family_handle:
                family = self.dbstate.db.get_family_from_handle(family_handle)
                family.remove_child_handle(self.active_person.get_handle())
                self.dbstate.db.commit_family(family,trans)

        handle = self.active_person.get_handle()

        person = self.active_person
        self.remove_from_person_list(person)
        #self.remove_from_history(handle)
        self.dbstate.db.remove_person(handle, trans)

        self.uistate.phistory.back()
        self.dbstate.db.transaction_commit(trans,_("Delete Person (%s)") % n)

    def build_columns(self):
        for column in self.columns:
            self.tree.remove_column(column)
        try:
            column = gtk.TreeViewColumn(
                _('Name'),
                self.renderer,text=0,
                foreground=self.model.marker_color_column)
            
        except AttributeError:
            column = gtk.TreeViewColumn(_('Name'), self.renderer,text=0)
            
        column.set_resizable(True)
        #column.set_clickable(True)
        #column.connect('clicked',self.sort_clicked)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(225)
        self.tree.append_column(column)
        self.columns = [column]

        for pair in self.dbstate.db.get_person_column_order():
            if not pair[0]:
                continue
            name = column_names[pair[1]]
            try:
                column = gtk.TreeViewColumn(
                    name, self.renderer, markup=pair[1],
                    foreground=self.model.marker_color_column)
            except AttributeError:
                column = gtk.TreeViewColumn(
                    name, self.renderer, markup=pair[1])
                
            column.set_resizable(True)
            column.set_fixed_width(pair[2])
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            self.columns.append(column)
            self.tree.append_column(column)

    def row_changed(self,obj):
        """Called with a row is changed. Check the selected objects from
        the person_tree to get the IDs of the selected objects. Set the
        active person to the first person in the list. If no one is
        selected, set the active person to None"""

        selected_ids = self.get_selected_objects()
        if not self.inactive:
            try:
                if len(selected_ids) == 0:
                    self.dbstate.change_active_person(None)
                else:
                    handle = selected_ids[0]
                    person = self.dbstate.db.get_person_from_handle(handle)
                    self.dbstate.change_active_person(person)
            except:
                pass

        if len(selected_ids) == 1:
            self.tree.drag_source_set(BUTTON1_MASK,
                                      [DdTargets.PERSON_LINK.target()],
                                      ACTION_COPY)
        elif len(selected_ids) > 1:
            self.tree.drag_source_set(BUTTON1_MASK,
                                      [DdTargets.PERSON_LINK_LIST.target()],
                                      ACTION_COPY)
        self.uistate.modify_statusbar(self.dbstate)
        
    def drag_data_get(self, widget, context, sel_data, info, time):
        selected_ids = self.get_selected_objects()
        nonempty_ids = [h for h in selected_ids if h]
        if nonempty_ids:
            data = (DdTargets.PERSON_LINK.drag_type, id(self),
                    nonempty_ids[0], 0)
            sel_data.set(sel_data.target, 8 ,pickle.dumps(data))

    def person_added(self,handle_list):
        if not self.model:
            return
        for node in handle_list:
            person = self.dbstate.db.get_person_from_handle(node)
            top = person.get_primary_name().get_group_name()
            self.model.rebuild_data()
            if not self.model.is_visable(node):
                continue
            if (not self.model.sname_sub.has_key(top) or 
                len(self.model.sname_sub[top]) == 1):
                path = self.model.on_get_path(top)
                pnode = self.model.get_iter(path)
                self.model.row_inserted(path,pnode)
            path = self.model.on_get_path(node)
            pnode = self.model.get_iter(path)
            self.model.row_inserted(path,pnode)

    def person_removed(self,handle_list):
        if not self.model:
            return
        
        self.model.clear_cache()
        for node in handle_list:
            person = self.dbstate.db.get_person_from_handle(node)
            top = person.get_primary_name().get_group_name()
            mylist = self.model.sname_sub.get(top,[])
            self.model.calculate_data(skip=set(handle_list))
            if mylist:
                try:
                    path = self.model.on_get_path(node)
                    self.model.row_deleted(path)
                    if len(mylist) == 1:
                        path = self.model.on_get_path(top)
                        self.model.row_deleted(path)
                except KeyError:
                    pass
            self.model.assign_data()
            
    def person_updated(self,handle_list):
        if not self.model:
            return
        
        self.model.clear_cache()
        for node in handle_list:
            person = self.dbstate.db.get_person_from_handle(node)
            try:
                oldpath = self.model.iter2path[node]
            except:
                return
            pathval = self.model.on_get_path(node)
            pnode = self.model.get_iter(pathval)

            # calculate the new data

            if person.primary_name.group_as:
                surname = person.primary_name.group_as
            else:
                base = person.primary_name.surname
                surname = self.dbstate.db.get_name_group_mapping(base)

            if oldpath[0] == surname:
		try:
		    self.model.build_sub_entry(surname)
		except:
		    self.model.calculate_data()
            else:
                self.model.calculate_data()
            
            # find the path of the person in the new data build
            newpath = self.model.temp_iter2path[node]
            
            # if paths same, just issue row changed signal

            if oldpath == newpath:
                self.model.row_changed(pathval,pnode)
            else:
                self.build_tree()
                break
            
        self.goto_active_person()

    def get_selected_objects(self):
        (mode,paths) = self.selection.get_selected_rows()
        mlist = []
        for path in paths:
            node = self.model.on_get_iter(path)
            handle = self.model.on_get_value(node, PeopleModel.COLUMN_INT_ID)
            if handle:
                mlist.append(handle)
        return mlist

    def remove_from_person_list(self,person):
        """Remove the selected person from the list. A person object is
        expected, not an ID"""
        path = self.model.on_get_path(person.get_handle())
        (col,row) = path
        if row > 0:
            self.selection.select_path((col,row-1))
        elif row == 0 and self.model.on_get_iter(path):
            self.selection.select_path(path)

    def button_press(self,obj,event):
        if event.type == gtk.gdk._2BUTTON_PRESS and event.button == 1:
            handle = self.first_selected()
            person = self.dbstate.db.get_person_from_handle(handle)
            if person:
                try:
                    EditPerson(self.dbstate, self.uistate, [], person)
                except Errors.WindowActiveError:
                    pass
                return True
        elif event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            menu = self.uistate.uimanager.get_widget('/Popup')
            if menu:
                menu.popup(None,None,None,event.button,event.time)
                return True
        return False

    def key_goto_home_person(self):
        self.home(None)
        self.uistate.push_message(self.dbstate,
                                  _("Go to default person"))

    def key_edit_selected_person(self):
        self.edit(None)
        self.uistate.push_message(self.dbstate,
                                  _("Edit selected person"))
